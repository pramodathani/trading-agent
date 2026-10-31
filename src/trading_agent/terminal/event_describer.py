"""Turns gateway events into short sentences for the activity feed and the chat.

It is a port of the web page's eventDescriber.ts, so the terminal and the browser describe events in the same words.

Typical usage example:

  description = EventDescriber().describe(event)
  description.title  # 'Risk engine refused: BUY 10 RELIANCE'
"""

import dataclasses
import json
from typing import Any

from trading_agent.terminal import formatter as formatter_module

_SOURCE_WORDS = {
    'user_message': 'Message from you',
    'cron': 'Woken by a scheduled job',
    'heartbeat': 'Heartbeat',
    'market_watcher': 'Woken by the market watcher',
    'webhook': 'Woken by a webhook',
    'rollover': 'Daily rollover',
    'compression': 'Context compression',
    'subagent': 'Woken by a subagent',
}
_QUIET_KINDS = (
    'turn_started',
    'turn_finished',
    'model_usage',
    'rate_limit',
    'trader_started',
    'account_status',
)


@dataclasses.dataclass(frozen=True)
class EventDescription:
    """One event in words.

    Attributes:
        title: A short title.
        detail: A longer detail, or an empty string.
        tone: How much attention it deserves: "normal", "quiet", "good", "warning" or "bad".
    """

    title: str
    detail: str
    tone: str


class EventDescriber:
    """Describes events by their kind and payload."""

    def __init__(self):
        """Creates the describer."""
        self._formatter = formatter_module.Formatter()

    def describe(self, event: dict[str, Any]) -> EventDescription:
        """Describes one event.

        Args:
            event (dict[str, Any]): The event, with kind, trader, payload and created_at.

        Returns:
            EventDescription: Its title, detail and tone.
        """
        kind = event.get('kind', '')
        payload = event.get('payload') or {}
        if kind == 'trigger_received':
            return self._make(
                self.source_words(payload.get('source')),
                self._text(payload.get('text')),
                'normal',
            )
        if kind == 'turn_started':
            return self._make('Turn started', '', 'quiet')
        if kind == 'turn_finished':
            return self._make('Turn finished', '', 'quiet')
        if kind == 'text':
            if payload.get('silent') is True:
                return self._make(
                    'Nothing to do', self._text(payload.get('text')), 'quiet'
                )
            return self._make(
                'Answered', self._text(payload.get('text')), 'normal'
            )
        if kind == 'tool_call':
            return self._make(
                f'Calls {self._text(payload.get("name"))}',
                self._json(payload.get('arguments')),
                'normal',
            )
        if kind == 'tool_result':
            name = self._text(payload.get('name'))
            if payload.get('is_error') is True:
                return self._make(
                    f'{name} failed', self._text(payload.get('text')), 'warning'
                )
            return self._make(
                f'{name} answered', self._text(payload.get('text')), 'quiet'
            )
        if kind == 'model_usage':
            prompt = self._formatter.number(payload.get('prompt_tokens'))
            answer = self._formatter.number(payload.get('completion_tokens'))
            return self._make(
                f'{self._text(payload.get("backend"))} used {prompt} prompt and {answer} answer tokens',
                '',
                'quiet',
            )
        if kind == 'rate_limit':
            return self._make(
                f'{self._text(payload.get("backend"))} {self._text(payload.get("limit"))} limit: {self._text(payload.get("status"))}',
                '',
                'quiet',
            )
        if kind == 'backend_unavailable':
            waiting = self._formatter.number(payload.get('waiting_seconds'))
            return self._make(
                f'{self._text(payload.get("backend"))} is unavailable; retrying in {waiting} s',
                self._text(payload.get('reason')),
                'warning',
            )
        if kind == 'backend_switch':
            if payload.get('from') is None:
                return self._make(
                    f'Model chosen: {self._text(payload.get("to"))}',
                    '',
                    'quiet',
                )
            return self._make(
                f'Model switched: {self._text(payload.get("from"))} → {self._text(payload.get("to"))}',
                '',
                'warning',
            )
        if kind == 'risk_decision':
            return self._risk_decision(payload)
        if kind == 'kill_switch':
            if payload.get('stage') == 'fired':
                return self._make(
                    'Kill switch fired',
                    self._text(payload.get('reason')),
                    'bad',
                )
            return self._make(
                'Kill switch: flatten finished',
                self._json(payload.get('outcome')),
                'bad',
            )
        if kind == 'order':
            return self._order(payload)
        if kind == 'fill':
            return self._fill(payload)
        if kind == 'price_alert':
            return self._price_alert(payload)
        if kind == 'trader_halt':
            return self._make(
                'Trader halted at its loss limit',
                self._text(payload.get('reason')),
                'bad',
            )
        if kind == 'account_status':
            return self._make(
                f'Account {self._formatter.money(payload.get("total_balance"))}, today {self._formatter.signed_money(payload.get("day_pnl"))}',
                '',
                'quiet',
            )
        if kind == 'session_started':
            session = self._text(payload.get('session_id'))
            if payload.get('reason') == 'resumed':
                return self._make(
                    f'Session {session} resumed after a restart', '', 'quiet'
                )
            return self._make(
                f'Session {session} started',
                self._text(payload.get('reason')).replace('_', ' '),
                'normal',
            )
        if kind == 'context_compressed':
            before = self._formatter.number(payload.get('tokens_before'))
            summarised = self._formatter.number(
                payload.get('messages_summarised')
            )
            return self._make(
                f'Conversation compressed from {before} tokens',
                f'{summarised} messages summarised',
                'normal',
            )
        if kind == 'subagent_started':
            return self._make(
                f'Subagent {self._text(payload.get("subagent"))} started',
                self._text(payload.get('task')),
                'normal',
            )
        if kind == 'subagent_finished':
            seconds = self._formatter.number(payload.get('seconds'))
            return self._make(
                f'Subagent {self._text(payload.get("subagent"))} {self._text(payload.get("outcome"))} in {seconds} s',
                '',
                'normal',
            )
        if kind == 'cron_fired':
            detail = ''
            if payload.get('catching_up') is True:
                detail = 'catching up a missed run'
            return self._make(
                f'Scheduled job: {self._text(payload.get("name"))}',
                detail,
                'normal',
            )
        if kind == 'cron_result':
            return self._make(
                f'Job {self._text(payload.get("name"))}: {self._text(payload.get("outcome"))}',
                self._text(payload.get('text')),
                'normal',
            )
        if kind == 'message':
            if payload.get('urgent') is True:
                return self._make(
                    'Urgent message', self._text(payload.get('text')), 'warning'
                )
            return self._make(
                'Message', self._text(payload.get('text')), 'normal'
            )
        if kind == 'error':
            return self._make(
                'The turn failed', self._text(payload.get('error')), 'bad'
            )
        if kind == 'steering':
            if payload.get('delivered') is True:
                return self._make(
                    'Your message was handed to the running turn', '', 'good'
                )
            return self._make(
                'The turn ended before your message reached it, so it is the next turn',
                '',
                'normal',
            )
        if kind == 'channel':
            return self._channel(payload)
        if kind == 'user_request':
            return self._user_request(payload)
        if kind == 'user_response':
            title = f'You answered a {self._text(payload.get("kind"))}'
            if payload.get('status') == 'dismissed':
                title = f'You dismissed a {self._text(payload.get("kind"))}'
            return self._make(title, self._text(payload.get('title')), 'good')
        if kind == 'stopped':
            return self._make('Turn stopped by you', '', 'warning')
        if kind == 'trader_started':
            return self._make('Trader started', '', 'quiet')
        if kind == 'trader_stopped':
            return self._make('Trader stopped', '', 'warning')
        tone = 'normal'
        if kind in _QUIET_KINDS:
            tone = 'quiet'
        return self._make(kind.replace('_', ' '), self._json(payload), tone)

    def source_words(self, source: object) -> str:
        """Names what woke a trader.

        Args:
            source (object): The trigger's source, such as "user_message".

        Returns:
            str: Plain words, such as "Message from you".
        """
        key = self._text(source)
        if key in _SOURCE_WORDS:
            return _SOURCE_WORDS[key]
        return f'Woken by {key.replace("_", " ")}'

    def _risk_decision(self, payload: dict[str, Any]) -> EventDescription:
        """Describes a risk engine decision.

        Args:
            payload (dict[str, Any]): The event's payload.

        Returns:
            EventDescription: The description.
        """
        order = self._text(payload.get('order'))
        if payload.get('approved') is True:
            return self._make(f'Risk engine approved: {order}', '', 'good')
        reasons = payload.get('reasons')
        detail = ''
        if isinstance(reasons, list):
            detail = ' '.join(str(reason) for reason in reasons)
        return self._make(f'Risk engine refused: {order}', detail, 'warning')

    def _order(self, payload: dict[str, Any]) -> EventDescription:
        """Describes an order action.

        Args:
            payload (dict[str, Any]): The event's payload.

        Returns:
            EventDescription: The description.
        """
        mode = ''
        if payload.get('dry_run') is True:
            mode = ' (dry run)'
        title = f'Order {self._text(payload.get("action"))}: {self._text(payload.get("kind"))}{mode}'
        lines = []
        if isinstance(payload.get('order'), str):
            lines.append(payload['order'])
        if isinstance(payload.get('steps'), list):
            for step in payload['steps']:
                lines.append(str(step))
        if isinstance(payload.get('reason'), str):
            lines.append(f'Reason: {payload["reason"]}')
        return self._make(title, '\n'.join(lines), 'good')

    def _fill(self, payload: dict[str, Any]) -> EventDescription:
        """Describes a fill report.

        Args:
            payload (dict[str, Any]): The event's payload.

        Returns:
            EventDescription: The description.
        """
        status = self._text(payload.get('status'))
        quantity = self._formatter.number(payload.get('filled_quantity'))
        price = self._formatter.price_text(payload.get('average_price'))
        tone = 'good'
        if status == 'REJECTED':
            tone = 'warning'
        return self._make(
            f'Order {status.lower()}: {quantity} at {price}',
            self._text(payload.get('message')),
            tone,
        )

    def _price_alert(self, payload: dict[str, Any]) -> EventDescription:
        """Describes a price alert that went off.

        Args:
            payload (dict[str, Any]): The event's payload.

        Returns:
            EventDescription: The description.
        """
        last_price = self._formatter.price_text(payload.get('last_price'))
        price = self._formatter.price_text(payload.get('price'))
        return self._make(
            f'{self._text(payload.get("symbol"))} at {last_price}, {self._text(payload.get("condition"))} {price}',
            self._text(payload.get('note')),
            'warning',
        )

    def _channel(self, payload: dict[str, Any]) -> EventDescription:
        """Describes a Telegram channel event.

        Args:
            payload (dict[str, Any]): The event's payload.

        Returns:
            EventDescription: The description.
        """
        name = self._text(payload.get('name'))
        if payload.get('action') == 'stranger':
            return self._make(
                f'Telegram: a chat that is not paired wrote ({name}, chat {self._text(payload.get("chat_id"))})',
                self._text(payload.get('text')),
                'warning',
            )
        if payload.get('action') == 'paired':
            return self._make(f'Telegram: paired {name}', '', 'good')
        return self._make(f'Telegram: connected as @{name}', '', 'quiet')

    def _user_request(self, payload: dict[str, Any]) -> EventDescription:
        """Describes a question, plan or permission request from a trader.

        Args:
            payload (dict[str, Any]): The event's payload, which is the whole request.

        Returns:
            EventDescription: The description.
        """
        content = payload.get('content')
        if not isinstance(content, dict):
            content = {}
        if payload.get('kind') == 'plan':
            return self._make(
                'The trader presented a plan for your approval',
                self._text(content.get('title')),
                'warning',
            )
        if payload.get('kind') == 'permission':
            return self._make(
                'The trader needs your permission',
                self._text(content.get('tool_name')),
                'warning',
            )
        return self._make('The trader asked you a question', '', 'warning')

    def _make(self, title: str, detail: str, tone: str) -> EventDescription:
        """Builds a description.

        Args:
            title (str): The title.
            detail (str): The detail.
            tone (str): The tone.

        Returns:
            EventDescription: The description.
        """
        return EventDescription(title=title, detail=detail, tone=tone)

    def _text(self, value: object) -> str:
        """Turns a payload value into text.

        Args:
            value (object): The value.

        Returns:
            str: The text, or an empty string for a missing value.
        """
        if value is None:
            return ''
        return str(value)

    def _json(self, value: object) -> str:
        """Turns a payload value into indented JSON.

        Args:
            value (object): The value.

        Returns:
            str: The JSON, or an empty string for a missing value or an empty mapping.
        """
        if value is None:
            return ''
        if isinstance(value, dict) and not value:
            return ''
        return json.dumps(value, indent=2, ensure_ascii=False)
