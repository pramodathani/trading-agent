"""The shallow base class of the browser tools, which share one desk's Chrome.

Typical usage example:

  class BrowserOpenTool(BrowserTool):
      ...
"""

from collections.abc import Awaitable

from trading_agent.extensions import untrusted_text
from trading_agent.tools import address_guard
from trading_agent.tools import browser_session as browser_session_module
from trading_agent.tools import tool

_BROWSER_TIMEOUT_SECONDS = 90.0


class BrowserTool(tool.Tool):
    """A tool that works on the desk's browser."""

    timeout_seconds = _BROWSER_TIMEOUT_SECONDS

    def __init__(self, session: browser_session_module.BrowserSession):
        """Creates the tool.

        Args:
            session (browser_session_module.BrowserSession): The desk's browser.
        """
        self._session = session

    async def _text_result(self, action: Awaitable[str]) -> tool.ToolResult:
        """Runs a browser action and turns its text, or its failure, into a tool result.

        Args:
            action (Awaitable[str]): The action, such as session.snapshot().

        Returns:
            tool.ToolResult: The action's text, or an error the model can act on.
        """
        try:
            text = await action
        except (
            browser_session_module.BrowserError,
            address_guard.AddressRefusedError,
        ) as error:
            return tool.ToolResult.error(str(error))
        return tool.ToolResult.success(
            untrusted_text.UntrustedText().wrap('a browser page', text)
        )
