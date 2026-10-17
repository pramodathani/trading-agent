"""Commands a user types to a desk, such as /status, answered by code with no model.

Typical usage example:

  commands = SlashCommands(desk, 'dry_run')
  reply = await commands.handle('/status')
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from trading_agent.backends import model_router
from trading_agent.runtime import trigger as trigger_module

if TYPE_CHECKING:
    from trading_agent.runtime import desk_runtime

_LATER_COMMANDS = {
    '/usage': 'milestone 15, with the usage tracker',
    '/think': 'a later milestone, with per-desk thinking settings',
    '/stop': 'a later milestone, with steering a running turn',
}


class SlashCommands:
    """The commands of one desk."""

    def __init__(self, desk: desk_runtime.DeskRuntime, mode: str):
        """Creates the commands for a desk.

        Args:
            desk (desk_runtime.DeskRuntime): The desk the commands act on.
            mode (str): "dry_run" or "live", reported by /status.
        """
        self._desk = desk
        self._mode = mode
        self._commands: dict[str, Callable[[str], Awaitable[str]]] = {
            '/help': self._help,
            '/status': self._status,
            '/new': self._new,
            '/compact': self._compact,
            '/model': self._model,
            '/pause': self._pause,
            '/resume': self._resume,
        }

    def is_command(self, text: str) -> bool:
        """Says whether a message is a command rather than something for the model.

        Args:
            text (str): The message.

        Returns:
            bool: True when it starts with a slash.
        """
        return text.strip().startswith('/')

    async def handle(self, text: str) -> str:
        """Runs one command.

        Args:
            text (str): The message, such as "/model qwen".

        Returns:
            str: The reply to show the user.
        """
        name, _, argument = text.strip().partition(' ')
        name = name.lower()
        command = self._commands.get(name)
        if command is not None:
            return await command(argument.strip())
        if name in _LATER_COMMANDS:
            return f'{name} is not available yet; it arrives in {_LATER_COMMANDS[name]}.'
        return f'Unknown command {name}. Type /help for the list.'

    async def _help(self, argument: str) -> str:
        """Lists the commands.

        Args:
            argument (str): Ignored.

        Returns:
            str: The list.
        """
        del argument
        return '\n'.join(
            [
                '/status              what the desk is doing and which models are ready',
                '/model               show the model order',
                '/model <name>        try that model first from now on',
                '/model auto          go back to the configured order',
                '/new                 forget this conversation and start a fresh one',
                '/compact             save what matters, then compress the conversation into a summary',
                '/pause               stop answering until /resume (commands still work)',
                '/resume              start answering again',
                '/help                this list',
            ]
        )

    async def _status(self, argument: str) -> str:
        """Describes the desk's state and its models.

        Args:
            argument (str): Ignored.

        Returns:
            str: The description.
        """
        del argument
        lines = [
            f'Desk: {self._desk.name}',
            f'Mode: {self._mode}',
            f'State: {self._desk.state}, paused: {"yes" if self._desk.paused else "no"}, triggers waiting: {self._desk.queued_count}',
        ]
        router = self._router()
        if router is None:
            lines.append('Models: none connected')
        else:
            if router.session_id is not None:
                lines.append(
                    f'Session: {router.session_id}, {len(router.exchanges)} exchange(s) so far'
                )
            lines.append('Models, in the order they will be tried:')
            lines.extend(router.status_lines())
        return '\n'.join(lines)

    async def _new(self, argument: str) -> str:
        """Forgets the desk's conversation.

        Args:
            argument (str): Ignored.

        Returns:
            str: A confirmation.
        """
        del argument
        await self._desk.turn_runner.reset()
        router = self._router()
        if router is not None and router.session_id is not None:
            return f'Started a fresh conversation, session {router.session_id}. The workspace files and Memory.md still apply.'
        return 'Started a fresh conversation. The workspace files still apply.'

    async def _compact(self, argument: str) -> str:
        """Compresses the conversation of the model that answered last.

        Args:
            argument (str): Ignored.

        Returns:
            str: What happened.
        """
        del argument
        trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.USER_MESSAGE,
            self._desk.name,
            '/compact',
        )
        return await self._desk.turn_runner.compact(trigger)

    async def _model(self, argument: str) -> str:
        """Shows or changes which model is tried first.

        Args:
            argument (str): Empty to show, a backend name to prefer it, or "auto".

        Returns:
            str: The order now in effect.
        """
        router = self._router()
        if router is None:
            return 'This desk has no models connected.'
        if argument:
            preferred = None if argument.lower() == 'auto' else argument
            try:
                router.prefer(preferred)
            except ValueError as error:
                return str(error)
        return '\n'.join(
            [
                'Models, in the order they will be tried:',
                *router.status_lines(),
            ]
        )

    async def _pause(self, argument: str) -> str:
        """Pauses the desk.

        Args:
            argument (str): Ignored.

        Returns:
            str: A confirmation.
        """
        del argument
        self._desk.paused = True
        return 'Paused. The desk will not ask any model until /resume. Commands still work.'

    async def _resume(self, argument: str) -> str:
        """Resumes the desk.

        Args:
            argument (str): Ignored.

        Returns:
            str: A confirmation.
        """
        del argument
        self._desk.paused = False
        return 'Resumed.'

    def _router(self) -> model_router.ModelRouter | None:
        """The desk's model router, when it has one.

        Returns:
            model_router.ModelRouter | None: The router, or None for a desk without models.
        """
        runner = self._desk.turn_runner
        if isinstance(runner, model_router.ModelRouter):
            return runner
        return None
