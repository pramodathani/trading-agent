"""Tests for the OpenAI-compatible backend's tool-call joining and message format."""

import json
from types import SimpleNamespace

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages
from trading_agent.backends import openai_compatible_backend
from trading_agent.configuration import agent_configuration


def _backend() -> openai_compatible_backend.OpenAICompatibleBackend:
    """Builds a backend pointed at a local address it never contacts.

    Returns:
        openai_compatible_backend.OpenAICompatibleBackend: The backend.
    """
    return openai_compatible_backend.OpenAICompatibleBackend(
        'local',
        agent_configuration.BackendConfiguration(
            kind='openai_compatible',
            base_url='http://127.0.0.1:9/v1',
            model='test-model',
            context_window=32768,
        ),
        api_key='',
    )


def _delta(
    index: int,
    call_id: str | None,
    name: str | None,
    arguments: str | None,
) -> SimpleNamespace:
    """Builds one streamed tool-call piece shaped like ChoiceDeltaToolCall.

    Args:
        index (int): The call's position in the reply.
        call_id (str | None): The call's identifier, sent in the first piece only.
        name (str | None): The tool's name, sent in the first piece only.
        arguments (str | None): A fragment of the arguments' JSON text.

    Returns:
        SimpleNamespace: The piece.
    """
    return SimpleNamespace(
        index=index,
        id=call_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


class TestOpenAICompatibleBackend:
    """Tests for OpenAICompatibleBackend."""

    def test_streamed_pieces_join_into_tool_calls(self) -> None:
        """Fragments of two calls, interleaved, join into two complete calls."""
        backend = _backend()
        parts = {}
        for piece in [
            _delta(0, 'call_a', 'get_quote', '{"sym'),
            _delta(1, 'call_b', 'get_time', ''),
            _delta(0, None, None, 'bol": "TCS"}'),
        ]:
            backend._add_call_delta(parts, piece)

        calls = [parts[index].to_tool_call() for index in sorted(parts)]

        assert calls[0] == messages.ToolCall(
            'call_a',
            'get_quote',
            {
                'symbol': 'TCS',
            },
        )
        assert calls[1].arguments == {}

    def test_broken_json_is_kept_for_the_model_to_see(self) -> None:
        """Arguments that are not JSON are kept as text instead of crashing the turn."""
        backend = _backend()
        parts = {}
        backend._add_call_delta(parts, _delta(0, 'call_a', 'echo', '{"word": '))

        call = parts[0].to_tool_call()

        assert call.arguments == {
            'unparseable_arguments': '{"word": ',
        }

    def test_wire_messages_use_ids_and_json_arguments(self) -> None:
        """Tool calls carry their id and JSON text; results point back at the id."""
        conversation = conversation_module.Conversation('be brief')
        call = messages.ToolCall(
            'call_a',
            'echo',
            {
                'word': 'x',
            },
        )
        conversation.append(messages.ConversationMessage.user('hi'))
        conversation.append(messages.ConversationMessage.assistant('', [call]))
        conversation.append(
            messages.ConversationMessage.tool_result(call, 'X', False)
        )

        wire = _backend()._wire_messages(conversation)

        assert wire[2]['tool_calls'][0]['id'] == 'call_a'
        assert json.loads(
            wire[2]['tool_calls'][0]['function']['arguments']
        ) == {
            'word': 'x',
        }
        assert wire[3] == {
            'role': 'tool',
            'tool_call_id': 'call_a',
            'content': 'X',
        }
