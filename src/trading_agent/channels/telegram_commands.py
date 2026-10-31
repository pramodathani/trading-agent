"""The Telegram commands answered by code, with no model.

These work even when every model is unavailable or a trader is paused, which is exactly when the user most needs them: what is happening, what is open, how much is made or lost, stop a trader, or stop everything. Any other message, including the traders' own slash commands such as /usage or /stop, goes to the chat's trader.

Typical usage example:

  commands = TelegramCommands(traders, shared, pairing, 'dry_run')
  if commands.handles('/pnl'):
      reply = await commands.answer(chat, '/pnl')
"""

import datetime
import zoneinfo
from collections.abc import Callable, Mapping

from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.gateway import gateway_parts
from trading_agent.requests import user_request as user_request_module
from trading_agent.requests import user_request_responder
from trading_agent.requests import user_request_store
from trading_agent.runtime import trader_runtime

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_KILL_CONFIRMATION = 'CONFIRM'
_ALL_TRADERS = 'all'
_COMMANDS = (
    '/start',
    '/help',
    '/trader',
    '/status',
    '/positions',
    '/pnl',
    '/pause',
    '/resume',
    '/kill',
    '/approve',
    '/deny',
)
_ALWAYS = 'always'
_MENU = (
    (
        'status',
        'Every trader, and the account',
    ),
    (
        'positions',
        'Open positions and which trader owns each',
    ),
    (
        'pnl',
        "Today's and this week's profit or loss, by trader",
    ),
    (
        'trader',
        'Talk to another trader: /trader <name>',
    ),
    (
        'stop',
        "Stop the trader's running turn",
    ),
    (
        'usage',
        "Today's model calls, tokens and costs",
    ),
    (
        'btw',
        "Ask a side question, not kept in the trader's conversation",
    ),
    (
        'review',
        "Have the trade reviewer judge today's trades",
    ),
    (
        'context',
        "How full the trader's context window is",
    ),
    (
        'tools',
        'The tools the trader can call',
    ),
    (
        'skills',
        'The skills the trader can follow',
    ),
    (
        'subagents',
        "The trader's subagents and today's runs",
    ),
    (
        'model',
        'Show or change the model order',
    ),
    (
        'think',
        'Show or set how hard the models think: /think [level]',
    ),
    (
        'compact',
        "Compress the trader's conversation",
    ),
    (
        'new',
        'Start a fresh conversation with the trader',
    ),
    (
        'pause',
        'Stop a trader asking its models: /pause [trader|all]',
    ),
    (
        'resume',
        'Start it again: /resume [trader|all]',
    ),
    (
        'approve',
        'Allow a held action: /approve [id] [always]',
    ),
    (
        'deny',
        'Refuse a held action: /deny [id] [reason]',
    ),
    (
        'kill',
        'Halt every trader and flatten: /kill CONFIRM <reason>',
    ),
    (
        'help',
        'Every command',
    ),
)


class TelegramCommands:
    """Answers the code-only commands of one gateway."""

    def __init__(
        self,
        traders: Mapping[str, trader_runtime.TraderRuntime],
        shared: gateway_parts.SharedParts,
        pairing: pairing_store_module.PairingStore,
        mode: str,
        clock: Callable[[], datetime.datetime] | None = None,
        request_store: user_request_store.UserRequestStore | None = None,
        responder: user_request_responder.UserRequestResponder | None = None,
    ):
        """Creates the commands.

        Args:
            traders (Mapping[str, trader_runtime.TraderRuntime]): The running traders.
            shared (gateway_parts.SharedParts): The snapshot reader, risk engine, ledger and kill switch.
            pairing (pairing_store_module.PairingStore): Where each chat's trader is kept.
            mode (str): "dry_run" or "live".
            clock (Callable[[], datetime.datetime] | None): Returns the current India time; None uses the system clock.
            request_store (user_request_store.UserRequestStore | None): The traders' requests, searched by /approve and /deny, or None.
            responder (user_request_responder.UserRequestResponder | None): Decides permission requests for /approve and /deny, or None.
        """
        self._traders = traders
        self._shared = shared
        self._pairing = pairing
        self._mode = mode
        self._clock = clock
        self._request_store = request_store
        self._responder = responder

    def handles(self, text: str) -> bool:
        """Says whether a message is one of these commands.

        Args:
            text (str): The message.

        Returns:
            bool: True for /start, /help, /trader, /status, /positions, /pnl, /pause, /resume, /kill, /approve and /deny.
        """
        return self._command_name(text) in _COMMANDS

    def menu(self) -> tuple[tuple[str, str], ...]:
        """The command menu Telegram shows when the user types a slash.

        Returns:
            tuple[tuple[str, str], ...]: Each command as (name without the slash, description).
        """
        return _MENU

    async def answer(
        self, chat: pairing_store_module.PairedChat, text: str
    ) -> str:
        """Answers a command.

        Args:
            chat (pairing_store_module.PairedChat): The paired chat that sent it.
            text (str): The command and its argument.

        Returns:
            str: The reply.
        """
        name = self._command_name(text)
        argument = text.strip()[len(text.strip().split()[0]) :].strip()
        if name == '/trader':
            return self._trader(chat, argument)
        if name == '/status':
            return await self._status(chat)
        if name == '/positions':
            return await self._positions()
        if name == '/pnl':
            return await self._pnl()
        if name == '/pause':
            return self._set_paused(chat, argument, True)
        if name == '/resume':
            return self._set_paused(chat, argument, False)
        if name == '/kill':
            return await self._kill(argument)
        if name == '/approve':
            return await self._decide(argument, True)
        if name == '/deny':
            return await self._decide(argument, False)
        return self._help(chat)

    async def _decide(self, argument: str, allow: bool) -> str:
        """Allows or refuses an action a trader is holding for permission.

        The request id may be left out when only one permission request is waiting, and may be shortened to its last six characters.

        Args:
            argument (str): An optional request id, then "always" for /approve or a reason for /deny.
            allow (bool): True for /approve, False for /deny.

        Returns:
            str: What was decided, or why nothing was.
        """
        if self._request_store is None or self._responder is None:
            return 'Permission requests are not handled on this gateway.'
        waiting = []
        for request in self._request_store.pending():
            if request.kind == user_request_module.PERMISSION:
                waiting.append(request)
        if not waiting:
            return 'No action is waiting for your permission.'
        words = argument.split(maxsplit=1)
        request = None
        rest = argument
        if words:
            request = self._matching_request(words[0], waiting)
        if request is not None:
            rest = argument[len(words[0]) :].strip()
        elif len(waiting) == 1:
            request = waiting[0]
        else:
            return self._waiting_list(waiting)
        decision = 'deny'
        reason = rest
        if allow:
            decision = 'allow_once'
            reason = ''
            if rest.lower() == _ALWAYS:
                decision = 'always_allow'
        try:
            await self._responder.decide_permission(
                request.request_id, decision, reason, 'telegram'
            )
        except ValueError as error:
            return f'Could not decide request {request.request_id}: {error}'
        tool_name = request.content.get('tool_name')
        if decision == 'deny':
            return f'Denied {tool_name} for the {request.trader} trader. The trader is told.'
        if decision == 'always_allow':
            return f'Allowed {tool_name} for the {request.trader} trader, now and from now on until you revoke it on Settings. The trader is told the result.'
        return f'Allowed {tool_name} for the {request.trader} trader, this once. The trader is told the result.'

    def _matching_request(
        self,
        word: str,
        waiting: list[user_request_module.UserRequest],
    ) -> user_request_module.UserRequest | None:
        """Finds the waiting request a word names, by its whole id or its last six characters.

        Args:
            word (str): The word, such as "a1b2c3".
            waiting (list[user_request_module.UserRequest]): The waiting permission requests.

        Returns:
            user_request_module.UserRequest | None: The request, or None when the word names none.
        """
        for request in waiting:
            if word == request.request_id:
                return request
            if request.request_id.endswith(f'-{word}'):
                return request
        return None

    def _waiting_list(
        self, waiting: list[user_request_module.UserRequest]
    ) -> str:
        """Lists the waiting permission requests, for when the user must say which one.

        Args:
            waiting (list[user_request_module.UserRequest]): The waiting permission requests.

        Returns:
            str: One line per request, with the short id to use.
        """
        lines = [
            'Several actions are waiting. Name one, such as /approve a1b2c3:',
        ]
        for request in waiting:
            short_id = request.request_id.rsplit('-', 1)[-1]
            lines.append(
                f'{short_id} - {request.trader}: {request.content.get("tool_name")}'
            )
        return '\n'.join(lines)

    def _command_name(self, text: str) -> str:
        """The command word, without a @botname suffix Telegram adds in groups.

        Args:
            text (str): The message.

        Returns:
            str: Such as "/pnl", or an empty string when the message is not a command.
        """
        stripped = text.strip()
        if not stripped.startswith('/'):
            return ''
        return stripped.split()[0].split('@')[0].lower()

    def _help(self, chat: pairing_store_module.PairedChat) -> str:
        """Lists the commands.

        Args:
            chat (pairing_store_module.PairedChat): The chat.

        Returns:
            str: The list.
        """
        return '\n'.join(
            [
                f'You are talking to the {chat.trader} trader. Anything that is not one of these commands goes to it.',
                '',
                '/status - every trader, and the account',
                '/positions - open positions and which trader owns each',
                "/pnl - today's and this week's profit or loss, by trader",
                '/trader <name> - talk to another trader',
                '/pause [trader|all] - stop a trader asking its models',
                '/resume [trader|all] - start it again',
                '/kill CONFIRM <reason> - halt every trader until tomorrow and flatten the account',
                '/approve [id] [always] - allow an action a trader is holding for your permission',
                '/deny [id] [reason] - refuse it',
                '',
                'These go to your trader:',
                "/stop - stop the trader's running turn",
                "/btw <question> - a side question, answered beside the trader's work and not kept",
                "/review [notes] - the trade reviewer judges today's orders and fills",
                "/usage - today's model calls, tokens and costs",
                "/context - how full the trader's context window is",
                '/tools, /skills, /subagents - what the trader can use',
                '/model [name|auto] - show or change the model order',
                '/think [off|low|medium|high|xhigh|max|default] - how hard the models think',
                "/compact - compress the trader's conversation",
                '/new - start a fresh conversation',
                '/rollover - summarise the day and start a fresh session',
                '/<skill-name> - ask the trader to follow one of its skills',
            ]
        )

    def _trader(
        self, chat: pairing_store_module.PairedChat, argument: str
    ) -> str:
        """Shows or changes the chat's trader.

        Args:
            chat (pairing_store_module.PairedChat): The chat.
            argument (str): The trader to talk to, or empty to show the current one.

        Returns:
            str: The reply.
        """
        names = ', '.join(self._traders)
        if not argument:
            return f'You are talking to {chat.trader}. The traders are {names}.'
        if argument not in self._traders:
            return f'There is no trader {argument!r}. The traders are {names}.'
        self._pairing.choose_trader(chat.chat_id, argument)
        return f'You are now talking to {argument}.'

    async def _status(self, chat: pairing_store_module.PairedChat) -> str:
        """Describes every trader and the account.

        Args:
            chat (pairing_store_module.PairedChat): The chat.

        Returns:
            str: The reply.
        """
        mode = 'LIVE ORDERS' if self._mode == 'live' else 'DRY RUN'
        lines = [
            f'Mode: {mode}',
        ]
        for name, trader in self._traders.items():
            marker = ' (yours)' if name == chat.trader else ''
            state = str(trader.state)
            if trader.paused:
                state = f'{state}, paused'
            if trader.queued_count:
                state = f'{state}, {trader.queued_count} waiting'
            lines.append(f'{name}{marker}: {state}')
        try:
            snapshot = await self._shared.snapshot_reader.read()
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            lines.append(f'Account: UBI cannot be read ({error}).')
            return '\n'.join(lines)
        lines.append(
            f'Account: {snapshot.total_balance:,.2f}, today {snapshot.day_pnl:+,.2f}, {len(snapshot.positions)} open positions.'
        )
        for halt in self._shared.ledger.halts_in_force(self._today()):
            lines.append(
                f'Halted ({halt["scope"]}) until {halt["until_date"]}: {halt["reason"]}'
            )
        return '\n'.join(lines)

    async def _positions(self) -> str:
        """Lists the open positions.

        Returns:
            str: The reply.
        """
        try:
            snapshot = await self._shared.snapshot_reader.read()
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            return f'UBI cannot be read: {error}'
        if not snapshot.positions:
            return 'No open positions.'
        owners = self._shared.ledger.owners()
        lines = []
        for position in snapshot.positions:
            owner = owners.get(position.instrument_id, 'yours')
            day = snapshot.day_pnl_by_instrument.get(position.instrument_id)
            day_text = f', today {day:+,.2f}' if day is not None else ''
            lines.append(
                f'{position.symbol} {position.product}: {position.quantity} at {position.last_price:,.2f}{day_text} ({owner})'
            )
        return '\n'.join(lines)

    async def _pnl(self) -> str:
        """Gives today's and this week's profit or loss.

        Returns:
            str: The reply.
        """
        try:
            snapshot = await self._shared.snapshot_reader.read()
        except ubi_exceptions.UnifiedBrokerInterfaceError as error:
            return f'UBI cannot be read: {error}'
        week = self._shared.ledger.week_pnl(self._today())
        lines = [
            f'Today: {snapshot.day_pnl:+,.2f}',
            f'This week: {week:+,.2f}',
        ]
        trader_pnl = self._shared.risk_engine.trader_day_pnl(snapshot)
        for name in self._traders:
            if name in trader_pnl:
                lines.append(f'{name}: {trader_pnl[name]:+,.2f}')
        return '\n'.join(lines)

    def _set_paused(
        self, chat: pairing_store_module.PairedChat, argument: str, paused: bool
    ) -> str:
        """Pauses or resumes a trader, or every trader.

        Args:
            chat (pairing_store_module.PairedChat): The chat.
            argument (str): A trader, "all", or empty for the chat's trader.
            paused (bool): True to pause, False to resume.

        Returns:
            str: The reply.
        """
        names = [
            argument or chat.trader,
        ]
        if argument == _ALL_TRADERS:
            names = list(self._traders)
        for name in names:
            if name not in self._traders:
                return f'There is no trader {name!r}.'
        for name in names:
            self._traders[name].paused = paused
        word = 'Paused' if paused else 'Resumed'
        return f'{word} {", ".join(names)}.'

    async def _kill(self, argument: str) -> str:
        """Fires the kill switch, if confirmed.

        Args:
            argument (str): CONFIRM followed by the reason.

        Returns:
            str: The reply.
        """
        words = argument.split(maxsplit=1)
        if not words or words[0] != _KILL_CONFIRMATION:
            return 'This halts every trader until tomorrow and flattens the whole account. To do it, send: /kill CONFIRM <reason>'
        reason = words[1] if len(words) > 1 else 'no reason given'
        now = self._now()
        outcome = await self._shared.kill_switch.trigger(
            f'The user fired the kill switch from Telegram: {reason}',
            now.date() + datetime.timedelta(days=1),
            now,
        )
        mode = ' as a dry run' if self._mode != 'live' else ''
        return f'Kill switch fired{mode}. Every trader is halted until tomorrow.\n{outcome}'

    def _today(self) -> datetime.date:
        """Today in India.

        Returns:
            datetime.date: The date.
        """
        return self._now().date()

    def _now(self) -> datetime.datetime:
        """The current India time.

        Returns:
            datetime.datetime: Now.
        """
        if self._clock is not None:
            return self._clock()
        return datetime.datetime.now(_INDIA)
