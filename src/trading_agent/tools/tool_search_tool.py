"""The tool_search tool: describes the MCP tools that match some keywords.

MCP tools are listed in the prompt by name only. This tool returns the full description and argument schema of the ones the desk asks about, so it can call them with call_mcp_tool.

Typical usage example:

  tool = ToolSearchTool(manager)
"""

import json

import pydantic

from trading_agent.extensions import mcp_client_manager
from trading_agent.tools import tool


class ToolSearchArguments(pydantic.BaseModel):
    """The arguments of tool_search.

    Attributes:
        query: Keywords, a tool name, or a server name to see all of its tools.
        limit: The most tools to describe.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    query: str = pydantic.Field(min_length=1)
    limit: int = pydantic.Field(default=5, gt=0, le=20)


class ToolSearchTool(tool.Tool):
    """Finds MCP tools and returns how to call them."""

    name = 'tool_search'
    description = "Describes the tools from MCP servers that match your keywords: each tool's server, name, description and JSON argument schema. Give keywords, a tool name, or a server name to see all of its tools. Then run a tool with call_mcp_tool."
    arguments_model = ToolSearchArguments

    def __init__(self, manager: mcp_client_manager.McpClientManager):
        """Creates the tool.

        Args:
            manager (mcp_client_manager.McpClientManager): The gateway's MCP connections.
        """
        self._manager = manager

    async def run(self, arguments: ToolSearchArguments) -> tool.ToolResult:
        """Ranks the tools by how many keywords they contain.

        Args:
            arguments (ToolSearchArguments): The query and the limit.

        Returns:
            tool.ToolResult: The matching tools with their schemas, or the names of all tools when nothing matches.
        """
        tools = self._manager.tools()
        if not tools:
            return tool.ToolResult.error(
                'No MCP server is ready, so there are no MCP tools right now.'
            )
        words = arguments.query.lower().split()
        scored = []
        for candidate in tools:
            if candidate.server.lower() == arguments.query.strip().lower():
                scored.append((len(words) + 1, candidate))
                continue
            haystack = f'{candidate.server} {candidate.name} {candidate.description}'.lower()
            score = 0
            for word in words:
                if word in haystack:
                    score += 1
            if score:
                scored.append((score, candidate))
        if not scored:
            names = []
            for candidate in tools:
                names.append(f'{candidate.server}/{candidate.name}')
            return tool.ToolResult.success(
                f'No MCP tool matches {arguments.query!r}. The tools are: {", ".join(names)}.'
            )
        scored.sort(key=lambda pair: pair[0], reverse=True)
        lines = []
        for _, candidate in scored[: arguments.limit]:
            lines.append(f'server: {candidate.server}')
            lines.append(f'tool: {candidate.name}')
            lines.append(f'description: {candidate.description}')
            lines.append(
                f'arguments schema: {json.dumps(candidate.input_schema, ensure_ascii=False)}'
            )
            lines.append('')
        return tool.ToolResult.success('\n'.join(lines).strip())
