"""The jev_decision tool: Jev's buy, sell or hold call on NIFTY right now.

Only traders whose trader.toml sets jev_signals get this tool.

Typical usage example:

  tool = JevDecisionTool(adviser)
"""

from trading_agent.tools import tool
from trading_agent.trading import jev_adviser as jev_adviser_module


class JevDecisionTool(tool.Tool):
    """Asks Jev whether NIFTY is a buy, a sell or a hold now."""

    name = 'jev_decision'
    description = "Asks Jev, TypeSafe AI's decision model, whether the NIFTY index is a buy, a sell or a hold for the next 5 to 15 minutes. The tool itself reads NIFTY's live quote and latest 5-minute candles from UBI and shows them to Jev, so it takes no arguments. Returns Jev's choice, its confidence from 0 to 1 and the probability of each answer. Jev only judges direction: you still choose the option, size, stop and target. Read-only; it places no order."
    arguments_model = tool.NoArguments
    timeout_seconds = 60.0

    def __init__(self, adviser: jev_adviser_module.JevAdviser):
        """Creates the tool.

        Args:
            adviser (jev_adviser_module.JevAdviser): Reads NIFTY's state and asks Jev.
        """
        self._adviser = adviser

    async def run(self, arguments: tool.NoArguments) -> tool.ToolResult:
        """Asks Jev.

        Args:
            arguments (tool.NoArguments): None.

        Returns:
            tool.ToolResult: Jev's decision, or an error saying why there is none.
        """
        del arguments
        try:
            advice = await self._adviser.advise()
        except jev_adviser_module.JevAdviserError as error:
            return tool.ToolResult.error(
                f'No Jev decision: {error} Treat this as hold, and open nothing until Jev answers again.'
            )
        return tool.ToolResult.success(advice.describe())
