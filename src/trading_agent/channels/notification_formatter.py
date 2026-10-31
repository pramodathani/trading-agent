"""Turns the events worth a phone notification into short messages.

The user chooses which kinds are pushed in trading_agent.toml's [telegram] notifications list. Every message starts with the trader's name, because one chat hears from every trader.

Typical usage example:

  formatter = NotificationFormatter(['fills', 'halts'])
  text = formatter.format(event, trigger_source)
"""

from collections.abc import Sequence

from trading_agent.runtime import event as event_module
from trading_agent.runtime import trigger as trigger_module

_REPORT_SOURCES = (
    trigger_module.TriggerSource.CRON,
    trigger_module.TriggerSource.HEARTBEAT,
    trigger_module.TriggerSource.MARKET_WATCHER,
    trigger_module.TriggerSource.WEBHOOK,
)


class NotificationFormatter:
    """Decides which events are pushed and how they read."""

    def __init__(self, notifications: Sequence[str]):
        """Creates the formatter.

        Args:
            notifications (Sequence[str]): The kinds to push, from [telegram] notifications.
        """
        self._notifications = set(notifications)

    def format(
        self,
        published_event: event_module.Event,
        trigger_source: str | None,
        trigger_text: str | None,
    ) -> str | None:
        """Builds the notification for one event.

        Args:
            published_event (event_module.Event): The event.
            trigger_source (str | None): For a text event, what woke the trader for that turn, or None when unknown.
            trigger_text (str | None): For a text event, the trigger's text, or None when unknown.

        Returns:
            str | None: The message, or None when this event is not pushed.
        """
        kind = published_event.kind
        payload = published_event.payload
        trader = published_event.trader or 'account'
        if kind == event_module.EventKind.FILL and self._wants('fills'):
            return self._fill(trader, payload)
        if (
            kind == event_module.EventKind.RISK_DECISION
            and not payload.get('approved')
            and self._wants('rejections')
        ):
            reasons = ' '.join(
                str(reason) for reason in payload.get('reasons', [])
            )
            return f'{trader}: the risk engine refused {payload.get("order", "an order")}. {reasons}'
        if (
            kind == event_module.EventKind.BACKEND_SWITCH
            and payload.get('from')
            and self._wants('model_switches')
        ):
            return f'{trader}: switched model from {payload.get("from")} to {payload.get("to")}.'
        if kind == event_module.EventKind.CRON_RESULT and self._wants(
            'job_results'
        ):
            return f'{trader}: job {payload.get("name")} finished ({payload.get("outcome")}).\n{payload.get("text", "")}'.strip()
        if kind == event_module.EventKind.TEXT and self._wants(
            'trader_reports'
        ):
            return self._report(trader, payload, trigger_source, trigger_text)
        if kind == event_module.EventKind.MESSAGE and self._wants('messages'):
            prefix = 'Message from'
            if payload.get('attachments'):
                prefix = 'Picture from'
            if payload.get('urgent'):
                prefix = 'URGENT from'
            return f'{prefix} {trader}:\n{payload.get("text", "")}'.strip()
        if kind == event_module.EventKind.PRICE_ALERT and self._wants('alerts'):
            note = f' Note: {payload["note"]}' if payload.get('note') else ''
            return f'{trader}: {payload.get("symbol")} traded at {payload.get("last_price")}, {payload.get("condition")} the alert at {payload.get("price")}.{note}'
        if kind == event_module.EventKind.TRADER_HALT and self._wants('halts'):
            return f'{trader} is halted for the day: {payload.get("reason")}'
        if (
            kind == event_module.EventKind.KILL_SWITCH
            and payload.get('stage') == 'fired'
            and self._wants('halts')
        ):
            mode = ' (dry run)' if payload.get('dry_run') else ''
            return f'KILL SWITCH fired{mode}: {payload.get("reason")}. Every trader is halted until {payload.get("until_date")}.'
        if kind == event_module.EventKind.ERROR and self._wants('errors'):
            return f'{trader}: a turn failed: {payload.get("error")}'
        return None

    def wants_daily_summaries(self) -> bool:
        """Says whether the day's summaries are pushed at each rollover.

        Returns:
            bool: True when daily_summaries is in the notifications list.
        """
        return self._wants('daily_summaries')

    def _wants(self, name: str) -> bool:
        """Says whether a kind of notification is switched on.

        Args:
            name (str): The kind.

        Returns:
            bool: True when it is in the notifications list.
        """
        return name in self._notifications

    def _fill(self, trader: str, payload: dict) -> str:
        """Describes a finished broker order.

        Args:
            trader (str): The trader.
            payload (dict): The fill event's payload.

        Returns:
            str: Such as "intraday: COMPLETE buy 10 INFY, 10 filled at 1501.2".
        """
        side = str(payload.get('transaction_type') or '').lower()
        order = f'{side} {payload.get("quantity", "")} {payload.get("symbol", "")}'.strip()
        line = f'{trader}: {payload.get("status")} {order}, {payload.get("filled_quantity")} filled at {payload.get("average_price")}'
        if payload.get('message'):
            line = f'{line}. {payload["message"]}'
        return line

    def _report(
        self,
        trader: str,
        payload: dict,
        trigger_source: str | None,
        trigger_text: str | None,
    ) -> str | None:
        """Describes what a trader said when it woke on its own, such as at a scheduled check.

        Args:
            trader (str): The trader.
            payload (dict): The text event's payload.
            trigger_source (str | None): What woke the trader.
            trigger_text (str | None): The trigger's text.

        Returns:
            str | None: The report, or None for answers to messages, silent heartbeats and commands such as /rollover.
        """
        if trigger_source not in _REPORT_SOURCES or payload.get('silent'):
            return None
        if trigger_text is not None and trigger_text.strip().startswith('/'):
            return None
        return f'{trader} ({trigger_source.replace("_", " ")}):\n{payload.get("text", "")}'
