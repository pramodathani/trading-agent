"""The cancel_price_alert tool: removes one of the desk's price alerts.

Typical usage example:

  tool = CancelPriceAlertTool(store)
"""

import pydantic

from trading_agent.scheduling import (
    price_alert_store as price_alert_store_module,
)
from trading_agent.tools import tool


class CancelPriceAlertArguments(pydantic.BaseModel):
    """The arguments of cancel_price_alert.

    Attributes:
        alert_id: The alert's id, as set_price_alert listed it.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    alert_id: str = pydantic.Field(min_length=1)


class CancelPriceAlertTool(tool.Tool):
    """Removes a price alert."""

    name = 'cancel_price_alert'
    description = (
        'Removes one of your price alerts by its id, and lists the ones left.'
    )
    arguments_model = CancelPriceAlertArguments

    def __init__(self, store: price_alert_store_module.PriceAlertStore):
        """Creates the tool.

        Args:
            store (price_alert_store_module.PriceAlertStore): The desk's alerts.
        """
        self._store = store

    async def run(
        self, arguments: CancelPriceAlertArguments
    ) -> tool.ToolResult:
        """Removes the alert.

        Args:
            arguments (CancelPriceAlertArguments): The alert's id.

        Returns:
            tool.ToolResult: A confirmation with the alerts left, or why nothing was removed.
        """
        removed = self._store.remove(arguments.alert_id)
        remaining = self._store.alerts()
        listing = (
            '; '.join(
                f'{alert.alert_id}: {alert.describe()}' for alert in remaining
            )
            or 'none'
        )
        if removed is None:
            return tool.ToolResult.error(
                f'No alert {arguments.alert_id}. Active alerts: {listing}.'
            )
        return tool.ToolResult.success(
            f'Removed {removed.describe()}. Active alerts: {listing}.'
        )
