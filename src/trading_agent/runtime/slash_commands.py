"""Commands a user types to a desk, such as /status, answered by code with no model.

Typical usage example:

  commands = SlashCommands(desk, 'dry_run')
  reply = await commands.handle('/status')
"""

import dataclasses
import datetime
import zoneinfo
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from trading_agent.backends import backend as backend_module
from trading_agent.backends import model_router
from trading_agent.journal import journal_reader as journal_reader_module
from trading_agent.runtime import event as event_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner as turn_runner_module
from trading_agent.skills import skill_library as skill_library_module
from trading_agent.subagents import subagent_library as subagent_library_module
from trading_agent.tools import tool_registry as tool_registry_module

if TYPE_CHECKING:
    from trading_agent.runtime import desk_runtime

_INSTANT_COMMANDS = (
    '/help',
    '/status',
    '/usage',
    '/context',
    '/tools',
    '/skills',
    '/subagents',
)
_BACKGROUND_COMMANDS = ('/btw',)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_FULL = 'full'
_DEFAULT = 'default'


@dataclasses.dataclass(frozen=True)
class CommandParts:
    """The parts of the gateway some commands read, beyond the desk itself.

    Attributes:
        tool_registry: The desk's tools, listed by /tools, or None.
        subagent_library: The subagents the desk can delegate to, listed by /subagents, or None.
        journal_reader: The desk's journal, read by /subagents, or None.
    """

    tool_registry: tool_registry_module.ToolRegistry | None = None
    subagent_library: subagent_library_module.SubagentLibrary | None = None
    journal_reader: journal_reader_module.JournalReader | None = None


class SlashCommands:
    """The commands of one desk."""

    def __init__(
        self,
        desk: desk_runtime.DeskRuntime,
        mode: str,
        skill_library: skill_library_module.SkillLibrary | None = None,
        parts: CommandParts | None = None,
    ):
        """Creates the commands for a desk.

        Args:
            desk (desk_runtime.DeskRuntime): The desk the commands act on.
            mode (str): "dry_run" or "live", reported by /status.
            skill_library (skill_library_module.SkillLibrary | None): The desk's skills, each of which can be invoked as /<skill-name>, or None.
            parts (CommandParts | None): The tools, subagents and journal some commands read, or None when none are available.
        """
        self._desk = desk
        self._mode = mode
        self._skill_library = skill_library
        self._parts = parts or CommandParts()
        self._background_command: str | None = None
        self._commands: dict[str, Callable[[str], Awaitable[str]]] = {
            '/help': self._help,
            '/status': self._status,
            '/new': self._new,
            '/compact': self._compact,
            '/rollover': self._rollover,
            '/usage': self._usage,
            '/model': self._model,
            '/pause': self._pause,
            '/resume': self._resume,
            '/think': self._think,
            '/btw': self._btw,
            '/context': self._context,
            '/tools': self._tools,
            '/skills': self._skills,
            '/subagents': self._subagents,
        }

    def is_command(self, text: str) -> bool:
        """Says whether a message is a command rather than something for the model.

        Args:
            text (str): The message.

        Returns:
            bool: True when it starts with a slash.
        """
        return text.strip().startswith('/')

    def command_name(self, text: str) -> str:
        """The command word of a message, lowercased and without the @botname suffix Telegram adds in groups.

        Args:
            text (str): The message, such as "/usage@my_bot today".

        Returns:
            str: The command word, such as "/usage", or an empty string for an empty message.
        """
        words = text.strip().split()
        if not words:
            return ''
        return words[0].split('@')[0].lower()

    def is_instant(self, text: str) -> bool:
        """Says whether a command only reads the desk, so it can be answered at once instead of waiting for the running turn.

        Args:
            text (str): The message.

        Returns:
            bool: True for the read-only commands, such as /status.
        """
        return self.command_name(text) in _INSTANT_COMMANDS

    def is_background(self, text: str) -> bool:
        """Says whether a command asks a model and runs beside the desk's turn, one at a time.

        Args:
            text (str): The message.

        Returns:
            bool: True for /btw.
        """
        return self.command_name(text) in _BACKGROUND_COMMANDS

    def skill_request(self, text: str) -> str | None:
        """Turns /<skill-name> into a request for the model to follow that skill.

        Built-in commands take precedence over skills of the same name.

        Args:
            text (str): The message, such as "/opening-range-breakout NIFTY".

        Returns:
            str | None: The text to send to the model, or None when the message does not name a usable skill.
        """
        if self._skill_library is None:
            return None
        name = self.command_name(text)
        argument = self._argument(text)
        if name in self._commands:
            return None
        skill = self._skill_library.find(name[1:])
        if skill is None:
            return None
        lines = [
            f'[The user invoked your skill {skill.name} with /{skill.name}. Load it with load_skill and follow it.]',
        ]
        if argument:
            lines.append(argument)
        return '\n'.join(lines)

    async def handle(self, text: str) -> str:
        """Runs one command.

        Args:
            text (str): The message, such as "/model qwen".

        Returns:
            str: The reply to show the user.
        """
        name = self.command_name(text)
        command = self._commands.get(name)
        if command is not None:
            return await command(self._argument(text))
        return f'Unknown command {name}. Type /help for the list.'

    def _argument(self, text: str) -> str:
        """The text after a message's command word.

        Args:
            text (str): The message, such as "/model qwen".

        Returns:
            str: The argument, such as "qwen", stripped of surrounding spaces.
        """
        words = text.strip().split(maxsplit=1)
        if len(words) < 2:
            return ''
        return words[1].strip()

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
                '/think               show how hard each model thinks',
                '/think <level>       off, low, medium, high, xhigh or max, from the next turn',
                '/think default       go back to the configured thinking',
                '/model               show the model order',
                '/model <name>        try that model first from now on',
                '/model auto          go back to the configured order',
                '/new                 forget this conversation and start a fresh one',
                '/compact             save what matters, then compress the conversation into a summary',
                '/rollover            summarise the day and start a fresh session now',
                "/usage               today's model calls, tokens, costs and Claude's limits",
                '/context             how full the context window is, and with what',
                '/tools [full]        the tools the desk can call',
                '/skills              the skills the desk can follow',
                "/subagents           the desk's subagents and today's runs",
                "/btw <question>      ask a side question; it is not kept in the desk's conversation",
                '/stop                stop the running turn at once (it skips the queue)',
                '/pause               stop answering until /resume (commands still work)',
                '/resume              start answering again',
                '/<skill-name> ...    ask the desk to follow one of its skills',
                '/help                this list',
                '',
                '/help, /status, /usage, /context, /tools, /skills and /subagents answer at once, even while the desk is working.',
                '/btw runs beside the desk, without waiting for or interrupting its turn.',
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

    async def _usage(self, argument: str) -> str:
        """Shows today's model usage.

        Args:
            argument (str): Ignored.

        Returns:
            str: The usage, or a note that no tracker is running.
        """
        del argument
        tracker = self._desk.usage_tracker
        if tracker is None:
            return 'Usage is not being tracked on this gateway.'
        return tracker.summary_text(self._desk.name)

    async def _rollover(self, argument: str) -> str:
        """Rolls the desk's session over now.

        Args:
            argument (str): Ignored.

        Returns:
            str: What happened.
        """
        del argument
        return await self._desk.roll_over()

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

    async def _think(self, argument: str) -> str:
        """Shows or changes how hard the desk's models think.

        Args:
            argument (str): Empty to show, a level from THINKING_LEVELS to set it, or "default" for trading_agent.toml's settings.

        Returns:
            str: Each backend's thinking level now in effect, or why the level was refused.
        """
        router = self._router()
        if router is None:
            return 'This desk has no models connected.'
        level = argument.lower()
        if level:
            levels = ', '.join(turn_runner_module.THINKING_LEVELS)
            if level == _DEFAULT:
                router.set_thinking(None)
            elif level in turn_runner_module.THINKING_LEVELS:
                router.set_thinking(level)
            else:
                return f'Unknown thinking level {argument!r}. Use one of {levels}, or default.'
        lines = [
            'Thinking, in the order the models will be tried:',
            *router.thinking_lines(),
        ]
        if level:
            lines.append(
                'This applies from the next turn and lasts until the gateway restarts.'
            )
        return '\n'.join(lines)

    async def _btw(self, argument: str) -> str:
        """Answers a side question from the desk's conversation without adding it to the conversation.

        Args:
            argument (str): The question.

        Returns:
            str: The answer and the backend that gave it, or why it was not asked.
        """
        if not argument:
            return 'Write the question after /btw, such as: /btw why did you sell INFY?'
        router = self._router()
        if router is None:
            return 'This desk has no models connected.'
        if self._desk.paused:
            return (
                'The desk is paused, so no model was asked. Send /resume first.'
            )
        if self._background_command is not None:
            return f'{self._background_command} is still running. Wait for its answer, then ask again.'
        self._background_command = '/btw'
        try:
            backend_name, answer = await router.side_question(argument)
        except backend_module.BackendUnavailableError as error:
            return f'No model could answer: {error}'
        finally:
            self._background_command = None
        return f"Side answer from {backend_name}, not kept in the desk's conversation:\n{answer}"

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

    async def _context(self, argument: str) -> str:
        """Shows how full the context window of the model that answered last is.

        Args:
            argument (str): Ignored.

        Returns:
            str: The window's size and what fills it, or a note that no turn has run yet.
        """
        del argument
        usage = self._desk.turn_runner.context_usage()
        if usage is None:
            return 'No turn has run in this session yet, so there is no context window to show.'
        how = 'measured by the model' if usage.measured else 'estimated'
        percent = 0
        if usage.context_window:
            percent = round(100 * usage.total_tokens / usage.context_window)
        lines = [
            f'Context window of {usage.model} ({usage.backend}), {how}:',
            f'{usage.total_tokens:,} of {usage.context_window:,} tokens used ({percent}%)',
        ]
        for category in usage.categories:
            line = f'  {category.name}: {category.tokens:,}'
            if category.deferred:
                line = f'{line} (listed, not loaded)'
            lines.append(line)
        recorded = datetime.datetime.fromisoformat(usage.recorded_at)
        lines.append(f'As of {recorded.astimezone(_INDIA):%H:%M} IST.')
        return '\n'.join(lines)

    async def _tools(self, argument: str) -> str:
        """Lists the tools the desk can call.

        Args:
            argument (str): "full" for whole descriptions; anything else gives the first sentence of each.

        Returns:
            str: One tool per line, or a note that the desk has no tools.
        """
        registry = self._parts.tool_registry
        if registry is None or not registry.tool_names:
            return 'This desk has no tools.'
        full = argument.lower() == _FULL
        lines = [
            f'{len(registry.tool_names)} tools:',
        ]
        for definition in registry.definitions():
            function = definition['function']
            description = function['description']
            if not full:
                description = self._first_sentence(description)
            lines.append(f'- {function["name"]}: {description}')
        if not full:
            lines.append('Send /tools full for the whole descriptions.')
        return '\n'.join(lines)

    async def _skills(self, argument: str) -> str:
        """Lists the desk's skills, the user's and its own, and the skills that cannot be used here.

        Args:
            argument (str): Ignored.

        Returns:
            str: The skills grouped by who wrote them, or a note that there are none.
        """
        del argument
        library = self._skill_library
        if library is None:
            return 'This desk has no skills.'
        yours = []
        own = []
        for skill in library.available():
            line = f'- /{skill.name}: {self._first_sentence(skill.description)}'
            if skill.origin == skill_library_module.AGENT:
                own.append(line)
            else:
                yours.append(line)
        hidden = []
        for hidden_skill in library.hidden():
            missing = ', '.join(hidden_skill.missing)
            hidden.append(f'- {hidden_skill.skill.name}: needs {missing}')
        if not yours and not own and not hidden:
            return 'This desk has no skills yet.'
        lines = []
        self._add_section(lines, 'Your skills:', yours)
        self._add_section(lines, "The desk's own skills:", own)
        self._add_section(lines, 'Skills that cannot be used here:', hidden)
        return '\n'.join(lines)

    async def _subagents(self, argument: str) -> str:
        """Lists the subagents the desk can delegate to, and today's subagent runs.

        Args:
            argument (str): Ignored.

        Returns:
            str: The subagents and runs, or a note that there are none.
        """
        del argument
        lines = []
        library = self._parts.subagent_library
        definitions = []
        if library is not None:
            for definition in library.definitions():
                definitions.append(
                    f'- {definition.name}: {self._first_sentence(definition.description)}'
                )
            for broken in library.broken():
                definitions.append(
                    f'- {broken.path.name} is broken: {broken.error}'
                )
        self._add_section(lines, 'Subagents:', definitions)
        self._add_section(lines, 'Runs today:', self._subagent_runs())
        if not lines:
            return 'This desk has no subagents and ran none today.'
        return '\n'.join(lines)

    def _subagent_runs(self) -> list[str]:
        """Describes today's subagent runs from the desk's journal, oldest first.

        Returns:
            list[str]: One line per run; a run with no finish event is shown as running.
        """
        reader = self._parts.journal_reader
        if reader is None:
            return []
        events = reader.events(
            reader.today(),
            (
                event_module.EventKind.SUBAGENT_STARTED,
                event_module.EventKind.SUBAGENT_FINISHED,
            ),
        )
        finished = {}
        for event in events:
            if event['kind'] == event_module.EventKind.SUBAGENT_FINISHED:
                finished[event['payload'].get('trigger_id')] = event['payload']
        lines = []
        for event in events:
            if event['kind'] != event_module.EventKind.SUBAGENT_STARTED:
                continue
            payload = event['payload']
            started = datetime.datetime.fromisoformat(event['created_at'])
            line = f'- {started.astimezone(_INDIA):%H:%M} {payload.get("subagent")}: '
            ending = finished.get(payload.get('trigger_id'))
            if ending is None:
                line = f'{line}running'
            else:
                line = f'{line}{ending.get("outcome")} on {ending.get("backend")} in {ending.get("seconds")} s'
            lines.append(line)
        return lines

    def _add_section(
        self,
        lines: list[str],
        heading: str,
        entries: list[str],
    ) -> None:
        """Adds a heading and its entries to a reply, with a blank line before it, unless there are no entries.

        Args:
            lines (list[str]): The reply's lines, extended in place.
            heading (str): The section's heading.
            entries (list[str]): The section's lines.
        """
        if not entries:
            return
        if lines:
            lines.append('')
        lines.append(heading)
        lines.extend(entries)

    def _first_sentence(self, text: str) -> str:
        """The first sentence of a description, for one-line lists.

        Args:
            text (str): The description.

        Returns:
            str: The text up to and including the first full stop that ends a sentence, or the first line when there is none.
        """
        stripped = text.strip()
        if not stripped:
            return ''
        first_line = stripped.splitlines()[0]
        end = first_line.find('. ')
        if end == -1:
            return first_line
        return first_line[: end + 1]

    def _router(self) -> model_router.ModelRouter | None:
        """The desk's model router, when it has one.

        Returns:
            model_router.ModelRouter | None: The router, or None for a desk without models.
        """
        runner = self._desk.turn_runner
        if isinstance(runner, model_router.ModelRouter):
            return runner
        return None
