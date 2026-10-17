"""The Telegram commands answered by code, with no model.

These work even when every model is unavailable or a desk is paused, which is exactly when the user most needs them: what is happening, what is open, how much is made or lost, stop a desk, or stop everything. Any other message, including the desks' own slash commands such as /usage or /stop, goes to the chat's desk.

Typical usage example:

  commands = TelegramCommands(desks, shared, pairing, 'dry_run')
  if commands.handles('/pnl'):
      reply = await commands.answer(chat, '/pnl')
"""

import datetime
import zoneinfo
from collections.abc import Callable, Mapping

from tradingmachine.unified_broker_interface import exceptions as ubi_exceptions

from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.gateway import gateway_parts
from trading_agent.runtime import desk_runtime

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_KILL_CONFIRMATION = 'CONFIRM'
_ALL_DESKS = 'all'
_COMMANDS = (
    '/start',
    '/help',
    '/desk',
    '/status',
    '/positions',
    '/pnl',
    '/pause',
    '/resume',
    '/kill',
)
_MENU = (
    (
        'status',
        'Every desk, and the account',
    ),
    (
        'positions',
        'Open positions and which desk owns each',
    ),
    (
        'pnl',
        "Today's and this week's profit or loss, by desk",
    ),
    (
        'desk',
        'Talk to another desk: /desk <name>',
    ),
    (
        'stop',
        "Stop the desk's running turn",
    ),
    (
        'usage',
        "Today's model calls, tokens and costs",
    ),
    (
        'context',
        "How full the desk's context window is",
    ),
    (
        'tools',
        'The tools the desk can call',
    ),
    (
        'skills',
        'The skills the desk can follow',
    ),
    (
        'subagents',
        "The desk's subagents and today's runs",
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
        "Compress the desk's conversation",
    ),
    (
        'new',
        'Start a fresh conversation with the desk',
    ),
    (
        'pause',
        'Stop a desk asking its models: /pause [desk|all]',
    ),
    (
        'resume',
        'Start it again: /resume [desk|all]',
    ),
    (
        'kill',
        'Halt every desk and flatten: /kill CONFIRM <reason>',
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
        desks: Mapping[str, desk_runtime.DeskRuntime],
        shared: gateway_parts.SharedParts,
        pairing: pairing_store_module.PairingStore,
        mode: str,
        clock: Callable[[], datetime.datetime] | None = None,
    ):
        """Creates the commands.

        Args:
            desks (Mapping[str, desk_runtime.DeskRuntime]): The running desks.
            shared (gateway_parts.SharedParts): The snapshot reader, risk engine, ledger and kill switch.
            pairing (pairing_store_module.PairingStore): Where each chat's desk is kept.
            mode (str): "dry_run" or "live".
            clock (Callable[[], datetime.datetime] | None): Returns the current India time; None uses the system clock.
        """
        self._desks = desks
        self._shared = shared
        self._pairing = pairing
        self._mode = mode
        self._clock = clock

    def handles(self, text: str) -> bool:
        """Says whether a message is one of these commands.

        Args:
            text (str): The message.

        Returns:
            bool: True for /start, /help, /desk, /status, /positions, /pnl, /pause, /resume and /kill.
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
        if name == '/desk':
            return self._desk(chat, argument)
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
        return self._help(chat)

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
                f'You are talking to the {chat.desk} desk. Anything that is not one of these commands goes to it.',
                '',
                '/status - every desk, and the account',
                '/positions - open positions and which desk owns each',
                "/pnl - today's and this week's profit or loss, by desk",
                '/desk <name> - talk to another desk',
                '/pause [desk|all] - stop a desk asking its models',
                '/resume [desk|all] - start it again',
                '/kill CONFIRM <reason> - halt every desk until tomorrow and flatten the account',
                '',
                'These go to your desk:',
                "/stop - stop the desk's running turn",
                "/usage - today's model calls, tokens and costs",
                "/context - how full the desk's context window is",
                '/tools, /skills, /subagents - what the desk can use',
                '/model [name|auto] - show or change the model order',
                '/think [off|low|medium|high|xhigh|max|default] - how hard the models think',
                "/compact - compress the desk's conversation",
                '/new - start a fresh conversation',
                '/rollover - summarise the day and start a fresh session',
                '/<skill-name> - ask the desk to follow one of its skills',
            ]
        )

    def _desk(
        self, chat: pairing_store_module.PairedChat, argument: str
    ) -> str:
        """Shows or changes the chat's desk.

        Args:
            chat (pairing_store_module.PairedChat): The chat.
            argument (str): The desk to talk to, or empty to show the current one.

        Returns:
            str: The reply.
        """
        names = ', '.join(self._desks)
        if not argument:
            return f'You are talking to {chat.desk}. The desks are {names}.'
        if argument not in self._desks:
            return f'There is no desk {argument!r}. The desks are {names}.'
        self._pairing.choose_desk(chat.chat_id, argument)
        return f'You are now talking to {argument}.'

    async def _status(self, chat: pairing_store_module.PairedChat) -> str:
        """Describes every desk and the account.

        Args:
            chat (pairing_store_module.PairedChat): The chat.

        Returns:
            str: The reply.
        """
        mode = 'LIVE ORDERS' if self._mode == 'live' else 'DRY RUN'
        lines = [
            f'Mode: {mode}',
        ]
        for name, desk in self._desks.items():
            marker = ' (yours)' if name == chat.desk else ''
            state = str(desk.state)
            if desk.paused:
                state = f'{state}, paused'
            if desk.queued_count:
                state = f'{state}, {desk.queued_count} waiting'
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
        desk_pnl = self._shared.risk_engine.desk_day_pnl(snapshot)
        for name in self._desks:
            if name in desk_pnl:
                lines.append(f'{name}: {desk_pnl[name]:+,.2f}')
        return '\n'.join(lines)

    def _set_paused(
        self, chat: pairing_store_module.PairedChat, argument: str, paused: bool
    ) -> str:
        """Pauses or resumes a desk, or every desk.

        Args:
            chat (pairing_store_module.PairedChat): The chat.
            argument (str): A desk, "all", or empty for the chat's desk.
            paused (bool): True to pause, False to resume.

        Returns:
            str: The reply.
        """
        names = [
            argument or chat.desk,
        ]
        if argument == _ALL_DESKS:
            names = list(self._desks)
        for name in names:
            if name not in self._desks:
                return f'There is no desk {name!r}.'
        for name in names:
            self._desks[name].paused = paused
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
            return 'This halts every desk until tomorrow and flattens the whole account. To do it, send: /kill CONFIRM <reason>'
        reason = words[1] if len(words) > 1 else 'no reason given'
        now = self._now()
        outcome = await self._shared.kill_switch.trigger(
            f'The user fired the kill switch from Telegram: {reason}',
            now.date() + datetime.timedelta(days=1),
            now,
        )
        mode = ' as a dry run' if self._mode != 'live' else ''
        return f'Kill switch fired{mode}. Every desk is halted until tomorrow.\n{outcome}'

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
