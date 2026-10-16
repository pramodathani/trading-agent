"""Holds a desk's tools and runs them by name.

The registry is the one place where a tool call from the model meets real code. It checks the arguments, applies a time limit, catches failures and caps the size of the output, so a misbehaving tool cannot crash the desk or flood the model's context.

Typical usage example:

  registry = ToolRegistry([GetTimeTool()], timeout_seconds=60)
  result = await registry.run(tool_call)
"""

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import Any

import pydantic

from trading_agent.agent import messages
from trading_agent.tools import tool as tool_module

_LOGGER = logging.getLogger(__name__)
_MAXIMUM_OUTPUT_CHARACTERS = 20000


class ToolRegistry:
    """The tools available to one desk."""

    def __init__(
        self,
        tools: Sequence[tool_module.Tool],
        timeout_seconds: float,
    ):
        """Creates a registry.

        Args:
            tools (Sequence[tool_module.Tool]): The tools, each with a unique name.
            timeout_seconds (float): How long one tool call may run before it is stopped.

        Raises:
            ValueError: Two tools have the same name.
        """
        self._tools = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f'Duplicate tool name: {tool.name!r}')
            self._tools[tool.name] = tool
        self._timeout_seconds = timeout_seconds

    @property
    def tool_names(self) -> list[str]:
        """The names of the registered tools, in registration order."""
        return list(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        """Describes every tool in the function-calling format Ollama and OpenAI share.

        Returns:
            list[dict[str, Any]]: One {"type": "function", "function": {...}} entry per tool.
        """
        definitions = []
        for tool in self._tools.values():
            definitions.append(
                {
                    'type': 'function',
                    'function': {
                        'name': tool.name,
                        'description': tool.description,
                        'parameters': tool.input_schema(),
                    },
                }
            )
        return definitions

    async def run(self, call: messages.ToolCall) -> tool_module.ToolResult:
        """Runs one tool call and always returns a result, never raises.

        Args:
            call (messages.ToolCall): The call the model made.

        Returns:
            tool_module.ToolResult: The tool's output, or an error result the model can act on.
        """
        tool = self._tools.get(call.name)
        if tool is None:
            return tool_module.ToolResult.error(
                f'There is no tool named {call.name!r}. Available tools: {", ".join(self._tools)}.'
            )
        try:
            arguments = tool.arguments_model.model_validate(call.arguments)
        except pydantic.ValidationError as error:
            return tool_module.ToolResult.error(
                f'The arguments for {call.name} are invalid: {error}. You sent: {json.dumps(call.arguments)}'
            )
        try:
            result = await asyncio.wait_for(
                tool.run(arguments),
                timeout=self._timeout_for(tool),
            )
        except TimeoutError:
            return tool_module.ToolResult.error(
                f'{call.name} did not finish within {self._timeout_for(tool):g} seconds and was stopped.'
            )
        except Exception as error:
            _LOGGER.exception('Tool %s failed', call.name)
            return tool_module.ToolResult.error(
                f'{call.name} failed: {error!r}'
            )
        return self._capped(result)

    async def close(self) -> None:
        """Closes every tool, for example stopping the bash terminal."""
        for tool in self._tools.values():
            await tool.close()

    def _timeout_for(self, tool: tool_module.Tool) -> float:
        """The time limit for one tool's calls.

        Args:
            tool (tool_module.Tool): The tool.

        Returns:
            float: The tool's own limit when it sets one, otherwise the registry's default.
        """
        if tool.timeout_seconds is not None:
            return tool.timeout_seconds
        return self._timeout_seconds

    def _capped(
        self,
        result: tool_module.ToolResult,
    ) -> tool_module.ToolResult:
        """Shortens an output that is too long for the model's context.

        Args:
            result (tool_module.ToolResult): The tool's output.

        Returns:
            tool_module.ToolResult: The same result, cut to the maximum length with a note saying so.
        """
        if len(result.text) <= _MAXIMUM_OUTPUT_CHARACTERS:
            return result
        removed = len(result.text) - _MAXIMUM_OUTPUT_CHARACTERS
        text = (
            result.text[:_MAXIMUM_OUTPUT_CHARACTERS]
            + f'\n[output cut: {removed} more characters were left out]'
        )
        return tool_module.ToolResult(
            text=text,
            is_error=result.is_error,
            image_png=result.image_png,
        )
