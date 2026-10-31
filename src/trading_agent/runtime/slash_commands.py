"""Commands a user types to a trader, such as /status, answered by code with no model.

Typical usage example:

  commands = SlashCommands(trader, 'dry_run')
  reply = await commands.handle('/status')
"""

import dataclasses
import datetime
import json
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
from trading_agent.subagents import subagent_runner as subagent_runner_module
from trading_agent.tools import tool_registry as tool_registry_module

if TYPE_CHECKING:
    from trading_agent.runtime import trader_runtime

_INSTANT_COMMANDS = (
    '/help',
    '/status',
    '/usage',
    '/context',
    '/tools',
    '/skills',
    '/subagents',
)
_BACKGROUND_COMMANDS = (
    '/btw',
    '/review',
)
_REVIEWER = 'trade_reviewer'
_MOST_REVIEWED_EVENTS = 200
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_FULL = 'full'
_DEFAULT = 'default'


@dataclasses.dataclass(frozen=True)
class CommandHelp:
    """One line of /help: how a command is typed and what it does.

    Attributes:
        usage: How the command is typed, such as "/think <level>".
        description: What it does.
    """

    usage: str
    description: str

    def name(self) -> str:
        """The command word, such as "/think".

        Returns:
            str: The first word of the usage.
        """
        return self.usage.split()[0]

    def line(self) -> str:
        """The line /help prints for this command.

        Returns:
            str: The usage padded to 20 characters, a space, then the description.
        """
        return f'{self.usage:<20} {self.description}'


_COMMAND_HELP = (
    CommandHelp(
        '/status',
        'what the trader is doing and which models are ready',
    ),
    CommandHelp(
        '/think',
        'show how hard each model thinks',
    ),
    CommandHelp(
        '/think <level>',
        'off, low, medium, high, xhigh or max, from the next turn',
    ),
    CommandHelp(
        '/think default',
        'go back to the configured thinking',
    ),
    CommandHelp(
        '/model',
        'show the model order',
    ),
    CommandHelp(
        '/model <name>',
        'try that model first from now on',
    ),
    CommandHelp(
        '/model auto',
        'go back to the configured order',
    ),
    CommandHelp(
        '/new',
        'forget this conversation and start a fresh one',
    ),
    CommandHelp(
        '/compact',
        'save what matters, then compress the conversation into a summary',
    ),
    CommandHelp(
        '/rollover',
        'summarise the day and start a fresh session now',
    ),
    CommandHelp(
        '/usage',
        "today's model calls, tokens, costs and Claude's limits",
    ),
    CommandHelp(
        '/context',
        'how full the context window is, and with what',
    ),
    CommandHelp(
        '/tools [full]',
        'the tools the trader can call',
    ),
    CommandHelp(
        '/skills',
        'the skills the trader can follow',
    ),
    CommandHelp(
        '/subagents',
        "the trader's subagents and today's runs",
    ),
    CommandHelp(
        '/btw <question>',
        "ask a side question; it is not kept in the trader's conversation",
    ),
    CommandHelp(
        '/review [notes]',
        "have the trade reviewer judge today's orders and fills",
    ),
    CommandHelp(
        '/stop',
        'stop the running turn at once (it skips the queue)',
    ),
    CommandHelp(
        '/pause',
        'stop answering until /resume (commands still work)',
    ),
    CommandHelp(
        '/resume',
        'start answering again',
    ),
    CommandHelp(
        '/<skill-name> ...',
        'ask the trader to follow one of its skills',
    ),
    CommandHelp(
        '/help',
        'this list',
    ),
)


@dataclasses.dataclass(frozen=True)
class CommandParts:
    """The parts of the gateway some commands read, beyond the trader itself.

    Attributes:
        tool_registry: The trader's tools, listed by /tools, or None.
        subagent_library: The subagents the trader can delegate to, listed by /subagents, or None.
        journal_reader: The trader's journal, read by /subagents and /review, or None.
        subagent_runner: Runs the trade reviewer for /review, or None.
    """

    tool_registry: tool_registry_module.ToolRegistry | None = None
    subagent_library: subagent_library_module.SubagentLibrary | None = None
    journal_reader: journal_reader_module.JournalReader | None = None
    subagent_runner: subagent_runner_module.SubagentRunner | None = None


class SlashCommands:
    """The commands of one trader."""

    def __init__(
        self,
        trader: trader_runtime.TraderRuntime,
        mode: str,
        skill_library: skill_library_module.SkillLibrary | None = None,
        parts: CommandParts | None = None,
    ):
        """Creates the commands for a trader.

        Args:
            trader (trader_runtime.TraderRuntime): The trader the commands act on.
            mode (str): "dry_run" or "live", reported by /status.
            skill_library (skill_library_module.SkillLibrary | None): The trader's skills, each of which can be invoked as /<skill-name>, or None.
            parts (CommandParts | None): The tools, subagents and journal some commands read, or None when none are available.
        """
        self._trader = trader
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
            '/review': self._review,
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
        """Says whether a command only reads the trader, so it can be answered at once instead of waiting for the running turn.

        Args:
            text (str): The message.

        Returns:
            bool: True for the read-only commands, such as /status.
        """
        return self.command_name(text) in _INSTANT_COMMANDS

    def is_background(self, text: str) -> bool:
        """Says whether a command asks a model and runs beside the trader's turn, one at a time.

        Args:
            text (str): The message.

        Returns:
            bool: True for /btw and /review.
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

    def catalogue(self) -> list[dict[str, str]]:
        """Every command and usable skill, for a client's command menu.

        Returns:
            list[dict[str, str]]: One entry per /help line, then one per usable skill, each with name, usage, description, kind ("command" or "skill") and runs ("at_once", "beside" or "queued"; /stop is "at_once" because it skips the queue).
        """
        entries = []
        for entry in _COMMAND_HELP:
            name = entry.name()
            if name == '/<skill-name>':
                continue
            runs = 'queued'
            if name in _INSTANT_COMMANDS or name == '/stop':
                runs = 'at_once'
            elif name in _BACKGROUND_COMMANDS:
                runs = 'beside'
            entries.append(
                {
                    'name': name,
                    'usage': entry.usage,
                    'description': entry.description,
                    'kind': 'command',
                    'runs': runs,
                }
            )
        if self._skill_library is None:
            return entries
        for skill in self._skill_library.available():
            if f'/{skill.name}' in self._commands:
                continue
            entries.append(
                {
                    'name': f'/{skill.name}',
                    'usage': f'/{skill.name}',
                    'description': skill.description,
                    'kind': 'skill',
                    'runs': 'queued',
                }
            )
        return entries

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
        lines = []
        for entry in _COMMAND_HELP:
            lines.append(entry.line())
        lines.extend(
            [
                '',
                '/help, /status, /usage, /context, /tools, /skills and /subagents answer at once, even while the trader is working.',
                '/btw and /review run beside the trader, without waiting for or interrupting its turn.',
            ]
        )
        return '\n'.join(lines)

    async def _status(self, argument: str) -> str:
        """Describes the trader's state and its models.

        Args:
            argument (str): Ignored.

        Returns:
            str: The description.
        """
        del argument
        lines = [
            f'Trader: {self._trader.name}',
            f'Mode: {self._mode}',
            f'State: {self._trader.state}, paused: {"yes" if self._trader.paused else "no"}, triggers waiting: {self._trader.queued_count}',
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
        """Forgets the trader's conversation.

        Args:
            argument (str): Ignored.

        Returns:
            str: A confirmation.
        """
        del argument
        await self._trader.turn_runner.reset()
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
            self._trader.name,
            '/compact',
        )
        return await self._trader.turn_runner.compact(trigger)

    async def _usage(self, argument: str) -> str:
        """Shows today's model usage.

        Args:
            argument (str): Ignored.

        Returns:
            str: The usage, or a note that no tracker is running.
        """
        del argument
        tracker = self._trader.usage_tracker
        if tracker is None:
            return 'Usage is not being tracked on this gateway.'
        return tracker.summary_text(self._trader.name)

    async def _rollover(self, argument: str) -> str:
        """Rolls the trader's session over now.

        Args:
            argument (str): Ignored.

        Returns:
            str: What happened.
        """
        del argument
        return await self._trader.roll_over()

    async def _model(self, argument: str) -> str:
        """Shows or changes which model is tried first.

        Args:
            argument (str): Empty to show, a backend name to prefer it, or "auto".

        Returns:
            str: The order now in effect.
        """
        router = self._router()
        if router is None:
            return 'This trader has no models connected.'
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
        """Shows or changes how hard the trader's models think.

        Args:
            argument (str): Empty to show, a level from THINKING_LEVELS to set it, or "default" for trading_agent.toml's settings.

        Returns:
            str: Each backend's thinking level now in effect, or why the level was refused.
        """
        router = self._router()
        if router is None:
            return 'This trader has no models connected.'
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
        """Answers a side question from the trader's conversation without adding it to the conversation.

        Args:
            argument (str): The question.

        Returns:
            str: The answer and the backend that gave it, or why it was not asked.
        """
        if not argument:
            return 'Write the question after /btw, such as: /btw why did you sell INFY?'
        router = self._router()
        if router is None:
            return 'This trader has no models connected.'
        if self._trader.paused:
            return 'The trader is paused, so no model was asked. Send /resume first.'
        return await self._one_at_a_time(
            '/btw', self._ask_side_question, argument
        )

    async def _ask_side_question(self, question: str) -> str:
        """Asks the trader's models the side question.

        Args:
            question (str): The question.

        Returns:
            str: The answer and the backend that gave it, or why no model could answer.
        """
        router = self._router()
        if router is None:
            return 'This trader has no models connected.'
        try:
            backend_name, answer = await router.side_question(question)
        except backend_module.BackendUnavailableError as error:
            return f'No model could answer: {error}'
        return f"Side answer from {backend_name}, not kept in the trader's conversation:\n{answer}"

    async def _review(self, argument: str) -> str:
        """Has the trade reviewer subagent review the trader's orders and fills of today.

        Args:
            argument (str): Extra instructions for the reviewer, or empty.

        Returns:
            str: The reviewer's report, or why there is none.
        """
        runner = self._parts.subagent_runner
        reader = self._parts.journal_reader
        if runner is None or reader is None:
            return 'This trader cannot run the trade reviewer.'
        if self._trader.paused:
            return 'The trader is paused, so no model was asked. Send /resume first.'
        if not self._trading_events():
            return 'The trader has placed no orders today, so there is nothing to review.'
        return await self._one_at_a_time('/review', self._run_review, argument)

    async def _run_review(self, argument: str) -> str:
        """Runs the trade reviewer on today's orders and fills.

        Args:
            argument (str): Extra instructions for the reviewer, or empty.

        Returns:
            str: The reviewer's report, with its outcome, backend and duration.
        """
        report = await self._parts.subagent_runner.run_one(
            subagent_runner_module.SubagentTask(
                subagent=_REVIEWER,
                task=self._review_task(argument),
            )
        )
        backend_name = report.backend_name or 'no backend'
        heading = f'Trade review by {_REVIEWER} ({report.outcome}, {backend_name}, {report.seconds:.0f} s):'
        return f'{heading}\n{report.text}'

    def _review_task(self, argument: str) -> str:
        """Writes the reviewer's task: today's orders and fills from the journal, and the user's extra instructions.

        Args:
            argument (str): Extra instructions for the reviewer, or empty.

        Returns:
            str: The task.
        """
        events = self._trading_events()
        lines = [
            f"Review the {self._trader.name} trader's trading today, {self._parts.journal_reader.today()}.",
            'These are its order actions and fills from the journal, oldest first, with India times. An order with "dry_run": true was checked by UBI and never reached a broker.',
        ]
        if len(events) > _MOST_REVIEWED_EVENTS:
            lines.append(
                f'Only the latest {_MOST_REVIEWED_EVENTS} of {len(events)} events are listed; use get_orders for the rest.'
            )
            events = events[-_MOST_REVIEWED_EVENTS:]
        for event in events:
            created = datetime.datetime.fromisoformat(event['created_at'])
            details = json.dumps(
                event['payload'], ensure_ascii=False, default=str
            )
            lines.append(
                f'- {created.astimezone(_INDIA):%H:%M} {event["kind"]}: {details}'
            )
        lines.append(
            'Judge the day as a whole: which trades fit the rules, which did not, and what the trader should do differently tomorrow.'
        )
        if argument:
            lines.append(f'The user adds: {argument}')
        return '\n'.join(lines)

    def _trading_events(self) -> list[dict]:
        """Today's order and fill events from the trader's journal, oldest first.

        Returns:
            list[dict]: The events, or an empty list when the trader has no journal.
        """
        reader = self._parts.journal_reader
        if reader is None:
            return []
        return reader.events(
            reader.today(),
            (
                event_module.EventKind.ORDER,
                event_module.EventKind.FILL,
            ),
        )

    async def _one_at_a_time(
        self,
        name: str,
        work: Callable[[str], Awaitable[str]],
        argument: str,
    ) -> str:
        """Runs a background command unless another is still running on this trader.

        Args:
            name (str): The command, such as "/btw", named in the reply to a second request.
            work (Callable[[str], Awaitable[str]]): Does the command's work and returns its reply.
            argument (str): Passed to work.

        Returns:
            str: The work's reply, or a request to wait for the command still running.
        """
        if self._background_command is not None:
            return f'{self._background_command} is still running. Wait for its answer, then ask again.'
        self._background_command = name
        try:
            return await work(argument)
        finally:
            self._background_command = None

    async def _pause(self, argument: str) -> str:
        """Pauses the trader.

        Args:
            argument (str): Ignored.

        Returns:
            str: A confirmation.
        """
        del argument
        self._trader.paused = True
        return 'Paused. The trader will not ask any model until /resume. Commands still work.'

    async def _resume(self, argument: str) -> str:
        """Resumes the trader.

        Args:
            argument (str): Ignored.

        Returns:
            str: A confirmation.
        """
        del argument
        self._trader.paused = False
        return 'Resumed.'

    async def _context(self, argument: str) -> str:
        """Shows how full the context window of the model that answered last is.

        Args:
            argument (str): Ignored.

        Returns:
            str: The window's size and what fills it, or a note that no turn has run yet.
        """
        del argument
        usage = self._trader.turn_runner.context_usage()
        if usage is None:
            return 'No model has reported its context window since the gateway started. Each one reports it at the end of a turn.'
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
        """Lists the tools the trader can call.

        Args:
            argument (str): "full" for whole descriptions; anything else gives the first sentence of each.

        Returns:
            str: One tool per line, or a note that the trader has no tools.
        """
        registry = self._parts.tool_registry
        if registry is None or not registry.tool_names:
            return 'This trader has no tools.'
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
        """Lists the trader's skills, the user's and its own, and the skills that cannot be used here.

        Args:
            argument (str): Ignored.

        Returns:
            str: The skills grouped by who wrote them, or a note that there are none.
        """
        del argument
        library = self._skill_library
        if library is None:
            return 'This trader has no skills.'
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
            return 'This trader has no skills yet.'
        lines = []
        self._add_section(lines, 'Your skills:', yours)
        self._add_section(lines, "The trader's own skills:", own)
        self._add_section(lines, 'Skills that cannot be used here:', hidden)
        return '\n'.join(lines)

    async def _subagents(self, argument: str) -> str:
        """Lists the subagents the trader can delegate to, and today's subagent runs.

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
            return 'This trader has no subagents and ran none today.'
        return '\n'.join(lines)

    def _subagent_runs(self) -> list[str]:
        """Describes today's subagent runs from the trader's journal, oldest first.

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
        """The trader's model router, when it has one.

        Returns:
            model_router.ModelRouter | None: The router, or None for a trader without models.
        """
        runner = self._trader.turn_runner
        if isinstance(runner, model_router.ModelRouter):
            return runner
        return None
