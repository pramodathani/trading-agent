"""Chooses and builds the tools one subagent task may use.

A subagent gets tools from its trader:

- Without a `tools` list, a safe read-only set: market data, the web, the knowledge base, past sessions, skills and MCP tools.
- With a list, exactly the tools named. Order tools are given only this way, and they still go through the trader's risk engine under the trader's name.
- The bash tools get a fresh bash session for each task, in the trader's sandbox, so tasks running side by side never type into the same shell.
- delegate_task is never given, so a subagent cannot start subagents. The browser tools are never given, because each trader has one Chrome profile, which two tasks cannot drive at once.

Typical usage example:

  toolbox = SubagentToolbox(trader_tools, bash_session_factory, 60.0)
  prepared = toolbox.prepare(definition)
"""

import dataclasses
from collections.abc import Callable, Sequence

from trading_agent.subagents import subagent_definition as definition_module
from trading_agent.tools import bash_background_tool
from trading_agent.tools import bash_check_tool
from trading_agent.tools import bash_restart_tool
from trading_agent.tools import bash_run_tool
from trading_agent.tools import bash_session as bash_session_module
from trading_agent.tools import tool as tool_module
from trading_agent.tools import tool_registry

DEFAULT_TOOL_NAMES = (
    'get_time',
    'read_file',
    'web_search',
    'web_fetch',
    'search_instruments',
    'get_quote',
    'get_candles',
    'get_portfolio',
    'get_orders',
    'search_sessions',
    'search_knowledge',
    'load_skill',
    'tool_search',
    'call_mcp_tool',
)
_BASH_TOOL_NAMES = (
    'bash_run',
    'bash_background',
    'bash_check',
    'bash_restart',
)
_DELEGATE_TOOL_NAME = 'delegate_task'
_BROWSER_PREFIX = 'browser_'


@dataclasses.dataclass
class PreparedTools:
    """The tools of one subagent task.

    Attributes:
        registry: The task's tool registry.
        bash_session: The fresh bash session made for the task, to close afterwards, or None.
        refused: Tools the definition asked for that subagents may never have.
        unknown: Tools the definition asked for that the trader does not have.
    """

    registry: tool_registry.ToolRegistry
    bash_session: bash_session_module.BashSession | None
    refused: list[str]
    unknown: list[str]


class SubagentToolbox:
    """Builds subagent tool registries from a trader's tools."""

    def __init__(
        self,
        trader_tools: Sequence[tool_module.Tool],
        bash_session_factory: Callable[[], bash_session_module.BashSession],
        tool_timeout_seconds: float,
    ):
        """Creates the toolbox.

        Args:
            trader_tools (Sequence[tool_module.Tool]): The trader's tools, shared with its subagents.
            bash_session_factory (Callable[[], bash_session_module.BashSession]): Makes a new bash session in the trader's sandbox.
            tool_timeout_seconds (float): The default time limit of one tool call.
        """
        self._trader_tools = {}
        for trader_tool in trader_tools:
            self._trader_tools[trader_tool.name] = trader_tool
        self._bash_session_factory = bash_session_factory
        self._tool_timeout_seconds = tool_timeout_seconds

    def prepare(
        self,
        definition: definition_module.SubagentDefinition,
    ) -> PreparedTools:
        """Builds the registry for one task.

        Args:
            definition (definition_module.SubagentDefinition): The subagent.

        Returns:
            PreparedTools: The registry and what was left out.
        """
        names = definition.tool_names
        if names is None:
            names = DEFAULT_TOOL_NAMES
        tools = []
        refused = []
        unknown = []
        bash_session = None
        for name in names:
            if name == _DELEGATE_TOOL_NAME or name.startswith(_BROWSER_PREFIX):
                refused.append(name)
                continue
            if name in _BASH_TOOL_NAMES:
                if bash_session is None:
                    bash_session = self._bash_session_factory()
                tools.append(self._bash_tool(name, bash_session))
                continue
            trader_tool = self._trader_tools.get(name)
            if trader_tool is None:
                if definition.tool_names is not None:
                    unknown.append(name)
                continue
            tools.append(trader_tool)
        return PreparedTools(
            registry=tool_registry.ToolRegistry(
                tools,
                timeout_seconds=self._tool_timeout_seconds,
            ),
            bash_session=bash_session,
            refused=refused,
            unknown=unknown,
        )

    def _bash_tool(
        self,
        name: str,
        session: bash_session_module.BashSession,
    ) -> tool_module.Tool:
        """Builds one bash tool on a task's own session.

        Args:
            name (str): One of the bash tool names.
            session (bash_session_module.BashSession): The task's session.

        Returns:
            tool_module.Tool: The tool.
        """
        if name == 'bash_run':
            return bash_run_tool.BashRunTool(session)
        if name == 'bash_background':
            return bash_background_tool.BashBackgroundTool(session)
        if name == 'bash_check':
            return bash_check_tool.BashCheckTool(session)
        return bash_restart_tool.BashRestartTool(session)
