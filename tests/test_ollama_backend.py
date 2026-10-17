"""Tests for converting a conversation into Ollama's message format."""

from trading_agent.agent import conversation as conversation_module
from trading_agent.agent import messages
from trading_agent.backends import ollama_backend
from trading_agent.configuration import agent_configuration


class TestOllamaBackend:
    """Tests for OllamaBackend's message conversion."""

    def test_wire_messages_cover_every_role(self) -> None:
        """System, user, assistant tool calls and tool results all reach Ollama in its shape."""
        backend = ollama_backend.OllamaBackend(
            'gemma',
            agent_configuration.BackendConfiguration(
                kind='ollama',
                base_url='http://127.0.0.1:11434',
                model='gemma4:31b',
                context_window=32768,
            ),
        )
        conversation = conversation_module.Conversation('be brief')
        call = messages.ToolCall.new('get_time', {})
        conversation.append(messages.ConversationMessage.user('time?'))
        conversation.append(messages.ConversationMessage.assistant('', [call]))
        conversation.append(
            messages.ConversationMessage.tool_result(call, '10:15', False)
        )

        wire = backend._wire_messages(conversation)

        assert wire == [
            {
                'role': 'system',
                'content': 'be brief',
            },
            {
                'role': 'user',
                'content': 'time?',
            },
            {
                'role': 'assistant',
                'content': '',
                'tool_calls': [
                    {
                        'function': {
                            'name': 'get_time',
                            'arguments': {},
                        },
                    },
                ],
            },
            {
                'role': 'tool',
                'content': '10:15',
                'tool_name': 'get_time',
            },
        ]

    def test_thinking_is_on_or_off(self) -> None:
        """off turns thinking off, any other level turns it on, and None goes back to the configured setting."""
        backend = ollama_backend.OllamaBackend(
            'qwen',
            agent_configuration.BackendConfiguration(
                kind='ollama',
                base_url='http://127.0.0.1:11434',
                model='qwen3.8:27b',
                context_window=32768,
            ),
        )

        backend.set_thinking('off')
        after_off = backend.thinking()
        backend.set_thinking('low')
        after_low = backend.thinking()
        backend.set_thinking('off')
        backend.set_thinking(None)

        assert after_off == 'off'
        assert after_low == 'on'
        assert backend.thinking() == 'on'
