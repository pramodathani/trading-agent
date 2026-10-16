"""Tests for running tool calls through the registry."""

import asyncio

import pytest

from tests import fakes
from trading_agent.agent import messages
from trading_agent.tools import get_time_tool
from trading_agent.tools import tool_registry


def _registry() -> tool_registry.ToolRegistry:
    """Builds a registry holding every fake tool, with a short timeout.

    Returns:
        tool_registry.ToolRegistry: The registry.
    """
    return tool_registry.ToolRegistry(
        [
            fakes.EchoTool(),
            fakes.CrashingTool(),
            fakes.SlowTool(),
            fakes.LongOutputTool(),
            get_time_tool.GetTimeTool(),
        ],
        timeout_seconds=0.05,
    )


def _run(name: str, arguments: dict) -> object:
    """Runs one call through a fresh registry.

    Args:
        name (str): The tool's name.
        arguments (dict): The call's arguments.

    Returns:
        object: The tool result.
    """
    call = messages.ToolCall.new(name, arguments)
    return asyncio.run(_registry().run(call))


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_valid_call_runs_the_tool(self) -> None:
        """A call with valid arguments returns the tool's output."""
        result = _run(
            'echo',
            {
                'word': 'nifty',
            },
        )

        assert result.text == 'NIFTY'
        assert not result.is_error

    def test_unknown_tool_is_an_error_listing_the_real_tools(self) -> None:
        """Calling a tool that does not exist tells the model which ones do."""
        result = _run('buy_everything', {})

        assert result.is_error
        assert 'echo' in result.text

    def test_invalid_arguments_are_an_error(self) -> None:
        """Arguments that do not match the schema are refused before the tool runs."""
        result = _run(
            'echo',
            {
                'wrod': 'typo',
            },
        )

        assert result.is_error
        assert 'invalid' in result.text

    def test_crashing_tool_is_an_error_not_an_exception(self) -> None:
        """A tool that raises becomes an error result."""
        result = _run('crash', {})

        assert result.is_error
        assert 'broken tool' in result.text

    def test_slow_tool_is_stopped(self) -> None:
        """A tool that runs past the timeout is stopped with an error result."""
        result = _run('slow', {})

        assert result.is_error
        assert 'did not finish' in result.text

    def test_long_output_is_cut(self) -> None:
        """An output longer than the limit is shortened, with a note saying so."""
        result = _run('long', {})

        assert len(result.text) < 21000
        assert 'output cut' in result.text

    def test_definitions_use_the_function_format(self) -> None:
        """Each definition has the type, name and JSON schema the models expect."""
        definitions = _registry().definitions()
        echo_definition = definitions[0]

        assert echo_definition['type'] == 'function'
        assert echo_definition['function']['name'] == 'echo'
        assert echo_definition['function']['parameters']['required'] == [
            'word',
        ]

    def test_duplicate_tool_names_are_refused(self) -> None:
        """Two tools with the same name cannot be registered together."""
        with pytest.raises(ValueError, match='Duplicate tool name'):
            tool_registry.ToolRegistry(
                [
                    fakes.EchoTool(),
                    fakes.EchoTool(),
                ],
                timeout_seconds=1,
            )

    def test_get_time_reports_india_time(self) -> None:
        """The time tool names the India time zone."""
        result = _run('get_time', {})

        assert 'IST' in result.text
