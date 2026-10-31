"""Tests for the DeepSeek backend: thinking sent back, pictures left out, cost by cache and hour, and a used-up credit."""

import asyncio
import datetime
from types import SimpleNamespace

import httpx
import openai
import pytest

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages
from trading_agent.backends import backend
from trading_agent.backends import deepseek_backend
from trading_agent.configuration import agent_configuration

_PEAK_MONDAY = datetime.datetime(2026, 10, 19, 7, 0, tzinfo=datetime.UTC)
_OFF_PEAK_MONDAY = datetime.datetime(2026, 10, 19, 12, 0, tzinfo=datetime.UTC)
_SATURDAY = datetime.datetime(2026, 10, 17, 7, 0, tzinfo=datetime.UTC)


def _backend(
    moment: datetime.datetime = _PEAK_MONDAY,
) -> deepseek_backend.DeepSeekBackend:
    """Builds a DeepSeek backend with V4 Pro's prices and a fixed clock, never contacting DeepSeek.

    Args:
        moment (datetime.datetime): What the clock says.

    Returns:
        deepseek_backend.DeepSeekBackend: The backend.
    """
    return deepseek_backend.DeepSeekBackend(
        'deepseek',
        agent_configuration.BackendConfiguration(
            kind='deepseek',
            base_url='http://127.0.0.1:9',
            model='deepseek-v4-pro',
            context_window=1000000,
            vision=False,
            usd_per_million_cache_hit_tokens=0.044,
            usd_per_million_cache_miss_tokens=1.32,
            usd_per_million_completion_tokens=3.96,
            peak_hours_utc=[
                '01:00-04:00',
                '06:00-10:00',
            ],
            off_peak_price_factor=0.5,
        ),
        'test-key',
        clock=lambda: moment,
    )


def _chunk(
    content: str | None = None, reasoning: str | None = None, usage=None
) -> SimpleNamespace:
    """Builds one streamed chunk shaped like DeepSeek's.

    Args:
        content (str | None): A piece of the answer.
        reasoning (str | None): A piece of the thinking.
        usage: The usage object on the last chunk, or None.

    Returns:
        SimpleNamespace: The chunk.
    """
    choices = []
    if content is not None or reasoning is not None:
        choices.append(
            SimpleNamespace(
                delta=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning,
                    tool_calls=None,
                ),
            )
        )
    return SimpleNamespace(choices=choices, usage=usage)


class _Stream:
    """An async iterator over fixed chunks, standing in for DeepSeek's stream."""

    def __init__(self, chunks: list):
        """Creates the stream.

        Args:
            chunks (list): The chunks to yield.
        """
        self._chunks = list(chunks)

    def __aiter__(self):
        """Returns the iterator.

        Returns:
            _Stream: Itself.
        """
        return self

    async def __anext__(self):
        """Gives the next chunk.

        Returns:
            SimpleNamespace: The chunk.

        Raises:
            StopAsyncIteration: When the chunks run out.
        """
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


def _replace_create(
    model_backend: deepseek_backend.DeepSeekBackend, create
) -> None:
    """Makes the backend's client call a stand-in instead of DeepSeek.

    Args:
        model_backend (deepseek_backend.DeepSeekBackend): The backend.
        create: The async stand-in for chat.completions.create.
    """
    model_backend._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


class TestDeepSeekBackend:
    """Tests for DeepSeekBackend."""

    def test_thinking_is_collected_and_cost_uses_the_cache_split(self) -> None:
        """Thinking pieces are joined apart from the answer, and the cost counts cached and uncached tokens separately."""
        model_backend = _backend()
        usage = SimpleNamespace(
            prompt_tokens=1_000_000,
            completion_tokens=100_000,
            prompt_cache_hit_tokens=900_000,
            prompt_cache_miss_tokens=100_000,
        )

        async def create(**arguments):
            """Returns a fixed stream.

            Args:
                **arguments: The request, ignored.

            Returns:
                _Stream: The chunks.
            """
            del arguments
            return _Stream(
                [
                    _chunk(reasoning='Check the '),
                    _chunk(reasoning='levels.'),
                    _chunk(content='Done.'),
                    _chunk(usage=usage),
                ]
            )

        _replace_create(model_backend, create)
        reply = asyncio.run(
            model_backend.complete(
                conversation_module.Conversation('system'),
                [],
                lambda piece: None,
            )
        )

        assert reply.text == 'Done.'
        assert reply.reasoning == 'Check the levels.'
        assert reply.cache_read_tokens == 900_000
        assert reply.cost_usd == pytest.approx(
            0.9 * 0.044 + 0.1 * 1.32 + 0.1 * 3.96
        )

    def test_off_peak_and_weekend_are_cheaper(self) -> None:
        """Off-peak hours and weekends cost the off-peak share of the peak price."""
        usage = SimpleNamespace(
            prompt_tokens=0,
            completion_tokens=1_000_000,
            prompt_cache_hit_tokens=0,
            prompt_cache_miss_tokens=0,
        )

        assert _backend(_PEAK_MONDAY)._cost_usd(usage, 0) == pytest.approx(3.96)
        assert _backend(_OFF_PEAK_MONDAY)._cost_usd(usage, 0) == pytest.approx(
            1.98
        )
        assert _backend(_SATURDAY)._cost_usd(usage, 0) == pytest.approx(1.98)

    def test_thinking_is_sent_back_with_assistant_messages(self) -> None:
        """An assistant message's thinking goes back as reasoning_content, as DeepSeek requires with tools."""
        conversation = conversation_module.Conversation('system')
        conversation.append(messages.ConversationMessage.user('Quote TCS'))
        call = messages.ToolCall('call_1', 'get_quote', {'symbol': 'TCS'})
        conversation.append(
            messages.ConversationMessage.assistant(
                '', [call], 'I need a quote.'
            )
        )
        conversation.append(
            messages.ConversationMessage.tool_result(call, '3,500', False)
        )

        wire = _backend()._wire_messages(conversation)

        assert wire[2]['reasoning_content'] == 'I need a quote.'
        assert 'reasoning_content' not in wire[1]

    def test_pictures_are_left_out_for_a_model_without_vision(self) -> None:
        """A picture is replaced by a note, because V4 Pro cannot see pictures."""
        conversation = conversation_module.Conversation('system')
        picture = messages.MessageImage('image/png', b'png')
        conversation.append(
            messages.ConversationMessage.user('Look', (picture,))
        )

        wire = _backend()._wire_messages(conversation)

        assert isinstance(wire[1]['content'], str)
        assert 'cannot see pictures' in wire[1]['content']

    def test_used_up_credit_waits_fifteen_minutes(self) -> None:
        """A 402 answer makes the router leave DeepSeek alone for 15 minutes."""
        model_backend = _backend()
        request = httpx.Request('POST', 'http://127.0.0.1:9/chat/completions')
        response = httpx.Response(
            402,
            request=request,
            json={'error': {'message': 'Insufficient Balance'}},
        )

        async def create(**arguments):
            """Raises DeepSeek's 402.

            Args:
                **arguments: The request, ignored.

            Raises:
                openai.APIStatusError: Always.
            """
            del arguments
            raise openai.APIStatusError(
                'Insufficient Balance', response=response, body=None
            )

        _replace_create(model_backend, create)
        with pytest.raises(backend.BackendUnavailableError) as raised:
            asyncio.run(
                model_backend.complete(
                    conversation_module.Conversation('system'),
                    [],
                    lambda piece: None,
                )
            )

        assert raised.value.retry_after_seconds == 900.0
        assert 'no credit' in str(raised.value)
