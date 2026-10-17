"""Hands a desk's tools to Claude Code as an in-process MCP server.

Claude Code calls each tool through the MCP protocol, but the call never leaves this process: the handler runs the call through the desk's ToolCallExecutor, so Claude's calls get the same loop guard, argument checks, time limit and output cap as Gemma's.

Typical usage example:

  bridge = ClaudeToolBridge(executor)
  server = bridge.build_server()
  bridge.current_trigger = trigger
"""

from typing import Any

import claude_agent_sdk

from trading_agent.agent import messages
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import tool_call_executor as tool_call_executor_module

SERVER_NAME = 'trading_agent'


class ClaudeToolHandler:
    """The handler Claude Code calls for one tool."""

    def __init__(self, bridge: ClaudeToolBridge, tool_name: str):
        """Creates the handler.

        Args:
            bridge (ClaudeToolBridge): The bridge that knows the current trigger and the executor.
            tool_name (str): The tool's name in the registry.
        """
        self._bridge = bridge
        self._tool_name = tool_name

    async def __call__(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Runs the tool call and returns the result in MCP's shape.

        Args:
            arguments (dict[str, Any]): The arguments Claude sent.

        Returns:
            dict[str, Any]: {"content": [{"type": "text", "text": ...}], "is_error": ...}.
        """
        call = messages.ToolCall.new(self._tool_name, dict(arguments))
        result = await self._bridge.executor.execute(
            self._bridge.current_trigger,
            call,
        )
        content = [
            {
                'type': 'text',
                'text': result.text,
            },
        ]
        if result.image is not None:
            content.append(
                {
                    'type': 'image',
                    'data': result.image.base64_data(),
                    'mimeType': result.image.media_type,
                }
            )
        return {
            'content': content,
            'is_error': result.is_error,
        }


class ClaudeToolBridge:
    """Builds the MCP server and remembers which trigger the current turn belongs to.

    Attributes:
        executor: What runs each call.
        current_trigger: The trigger of the turn in progress, set by the turn runner before each turn.
    """

    def __init__(self, executor: tool_call_executor_module.ToolCallExecutor):
        """Creates the bridge.

        Args:
            executor (tool_call_executor_module.ToolCallExecutor): What runs each call.
        """
        self.executor = executor
        self.current_trigger: trigger_module.Trigger | None = None

    def build_server(self) -> claude_agent_sdk.McpSdkServerConfig:
        """Builds the in-process MCP server holding every tool in the registry.

        Returns:
            claude_agent_sdk.McpSdkServerConfig: The server, for ClaudeAgentOptions.mcp_servers.
        """
        sdk_tools = []
        for definition in self.executor.tool_registry.definitions():
            function = definition['function']
            sdk_tools.append(
                claude_agent_sdk.SdkMcpTool(
                    name=function['name'],
                    description=function['description'],
                    input_schema=function['parameters'],
                    handler=ClaudeToolHandler(self, function['name']),
                )
            )
        return claude_agent_sdk.create_sdk_mcp_server(
            SERVER_NAME,
            tools=sdk_tools,
        )

    def claude_tool_names(self) -> list[str]:
        """The names Claude Code knows the tools by.

        Returns:
            list[str]: Each tool's name as "mcp__trading_agent__<name>".
        """
        names = []
        for name in self.executor.tool_registry.tool_names:
            names.append(f'mcp__{SERVER_NAME}__{name}')
        return names
