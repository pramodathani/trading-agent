"""Tests for the terminal program's chat screen, driven with Textual's test pilot and a stand-in gateway."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from trading_agent.terminal import gateway_client
from trading_agent.terminal import prompt_history
from trading_agent.terminal import terminal_application
from trading_agent.terminal import terminal_settings
from trading_agent.terminal.widgets import command_menu
from trading_agent.terminal.widgets import composer
from trading_agent.terminal.widgets import keys_screen
from trading_agent.terminal.widgets import progress_line
from trading_agent.terminal.widgets import turn_view

_SIZE = (
    120,
    40,
)


def _event(
    event_kind: str, desk: str = 'general', **payload: Any
) -> dict[str, Any]:
    """Makes one event.

    Args:
        event_kind (str): The event's kind.
        desk (str): The event's desk.
        **payload (Any): The event's payload.

    Returns:
        dict[str, Any]: The event.
    """
    return {
        'kind': event_kind,
        'desk': desk,
        'payload': payload,
        'created_at': '2026-10-19T04:30:00+00:00',
    }


class _StandInGateway(gateway_client.GatewayClient):
    """A gateway client that answers from memory and records what it was sent.

    Attributes:
        sent: The (desk, text) pairs sent as messages.
        model_choices: The (desk, backend, model) choices made.
        state: The desks' state, such as "idle" or "busy".
    """

    def __init__(self):
        """Creates the stand-in, with a stream address nothing listens on."""
        super().__init__('http://127.0.0.1:9', 'token')
        self.sent: list[tuple[str, str]] = []
        self.model_choices: list[tuple[str, str | None, str | None]] = []
        self.state = 'idle'

    async def desks(self) -> dict[str, Any]:
        """Two desks.

        Returns:
            dict[str, Any]: The desks document.
        """
        desks = []
        for name in ('general', 'intraday'):
            desks.append(
                {
                    'name': name,
                    'state': self.state,
                    'paused': False,
                    'queued': 0,
                    'preferred_model': None,
                    'last_model': 'claude',
                    'backends': [
                        {
                            'name': 'claude',
                            'kind': 'claude_code',
                            'model': 'opus',
                            'active_model': 'opus',
                            'other_models': [],
                        },
                    ],
                }
            )
        return {
            'mode': 'dry_run',
            'desks': desks,
        }

    async def desk_journal(
        self,
        desk_name: str,
        limit: int = 1500,
        day: str | None = None,
    ) -> dict[str, Any]:
        """One finished turn on the general desk, none on the others.

        Args:
            desk_name (str): The desk.
            limit (int): Ignored.
            day (str | None): Ignored.

        Returns:
            dict[str, Any]: The journal document.
        """
        del limit, day
        if desk_name != 'general':
            return {
                'events': [],
            }
        return {
            'events': [
                _event(
                    'trigger_received',
                    trigger_id='t1',
                    source='user_message',
                    text='hello',
                ),
                _event('turn_started', trigger_id='t1'),
                _event('text', trigger_id='t1', text='Hi there.'),
                _event('turn_finished', trigger_id='t1'),
            ],
        }

    async def desk_commands(self, desk_name: str) -> dict[str, Any]:
        """Two desk commands.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The commands document.
        """
        return {
            'desk': desk_name,
            'commands': [
                {
                    'name': '/status',
                    'usage': '/status',
                    'description': 'what the desk is doing',
                    'kind': 'command',
                    'runs': 'at_once',
                },
                {
                    'name': '/stop',
                    'usage': '/stop',
                    'description': 'stop the running turn',
                    'kind': 'command',
                    'runs': 'at_once',
                },
            ],
        }

    async def send_message(
        self,
        desk_name: str,
        text: str,
        attachment_ids: Any = (),
    ) -> str:
        """Records a message.

        Args:
            desk_name (str): The desk.
            text (str): The message.
            attachment_ids (Any): Ignored.

        Returns:
            str: A trigger id.
        """
        del attachment_ids
        self.sent.append(
            (
                desk_name,
                text,
            )
        )
        return f'sent-{len(self.sent)}'

    async def choose_model(
        self,
        desk_name: str,
        backend_name: str | None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Records a model choice.

        Args:
            desk_name (str): The desk.
            backend_name (str | None): The backend.
            model (str | None): The model.

        Returns:
            dict[str, Any]: An empty summary.
        """
        self.model_choices.append(
            (
                desk_name,
                backend_name,
                model,
            )
        )
        return {}


def _run(
    scenario: Callable[
        [terminal_application.TerminalApplication, Any, _StandInGateway],
        Awaitable[None],
    ],
    tmp_path: Path,
) -> _StandInGateway:
    """Runs a scenario against the program with a stand-in gateway.

    Args:
        scenario (Callable[[terminal_application.TerminalApplication, Any, _StandInGateway], Awaitable[None]]): Drives the program with the pilot.
        tmp_path (Path): A folder for the settings and history.

    Returns:
        _StandInGateway: The stand-in, with what it was sent.
    """
    gateway = _StandInGateway()

    async def run() -> None:
        """Starts the program, runs the scenario and stops."""
        program = terminal_application.TerminalApplication(
            gateway,
            terminal_settings.TerminalSettings(tmp_path / 'terminal.json'),
            prompt_history.PromptHistory(tmp_path / 'history'),
            'general',
        )
        async with program.run_test(size=_SIZE) as pilot:
            await pilot.pause(0.3)
            await scenario(program, pilot, gateway)

    asyncio.run(run())
    return gateway


class TestChatScreen:
    """Tests for loading, sending, commands and keys."""

    def test_journal_turns_are_shown(self, tmp_path: Path) -> None:
        """Today's journal becomes one turn view per trigger."""

        async def scenario(program, pilot, gateway) -> None:
            """Checks the turn views.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            del pilot, gateway
            views = program.screen.query(turn_view.TurnView)
            assert len(views) == 1
            assert views.first().trigger_id == 't1'

        _run(scenario, tmp_path)

    def test_enter_sends_and_history_recalls(self, tmp_path: Path) -> None:
        """Enter sends the message to the desk, and Up brings it back."""

        async def scenario(program, pilot, gateway) -> None:
            """Sends a message and recalls it.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            await pilot.press(*'buy nothing')
            await pilot.press('enter')
            await pilot.pause(0.2)
            box = program.screen.query_one(composer.Composer)
            assert box.text == ''
            await pilot.press('up')
            assert box.text == 'buy nothing'
            assert gateway.sent == [
                (
                    'general',
                    'buy nothing',
                ),
            ]

        _run(scenario, tmp_path)

    def test_slash_opens_the_menu_and_enter_completes(
        self, tmp_path: Path
    ) -> None:
        """Typing /st shows /status first; Enter completes it, and a second Enter sends it."""

        async def scenario(program, pilot, gateway) -> None:
            """Uses the command menu.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            await pilot.press('/', 's', 't')
            menu = program.screen.query_one(command_menu.CommandMenu)
            assert menu.display
            assert menu.highlighted_name() == '/status'
            await pilot.press('enter')
            box = program.screen.query_one(composer.Composer)
            assert box.text == '/status '
            await pilot.press('enter')
            await pilot.pause(0.2)
            assert gateway.sent[-1] == (
                'general',
                '/status',
            )

        _run(scenario, tmp_path)

    def test_desk_command_switches_desk_without_sending(
        self, tmp_path: Path
    ) -> None:
        """/desk intraday is handled by the terminal: the chat switches and nothing is sent."""

        async def scenario(program, pilot, gateway) -> None:
            """Switches desk.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            await pilot.pause(0.3)
            await pilot.press(*'/desk intraday')
            await pilot.press('enter')
            await pilot.pause(0.3)
            assert program.chat.desk_name == 'intraday'
            assert gateway.sent == []
            assert not program.screen.query(turn_view.TurnView)

        _run(scenario, tmp_path)

    def test_live_events_stream_and_escape_stops(self, tmp_path: Path) -> None:
        """A live running turn shows the progress line, and Escape sends /stop."""

        async def scenario(program, pilot, gateway) -> None:
            """Feeds a running turn and stops it.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            for event in [
                _event(
                    'trigger_received',
                    trigger_id='t2',
                    source='user_message',
                    text='think',
                ),
                _event('turn_started', trigger_id='t2'),
                _event('text_delta', trigger_id='t2', text='Working on'),
            ]:
                program.chat.take_event(event)
            await pilot.pause(0.2)
            line = program.screen.query_one(progress_line.ProgressLine)
            assert line.display
            await pilot.press('escape')
            await pilot.pause(0.2)
            assert gateway.sent[-1] == (
                'general',
                '/stop',
            )
            program.chat.take_event(
                _event('text', trigger_id='t2', text='Stopped.')
            )
            program.chat.take_event(_event('turn_finished', trigger_id='t2'))
            await pilot.pause(0.2)
            assert not line.display

        _run(scenario, tmp_path)

    def test_events_of_another_desk_are_ignored(self, tmp_path: Path) -> None:
        """An event of another desk does not appear in this desk's chat."""

        async def scenario(program, pilot, gateway) -> None:
            """Feeds another desk's trigger.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            del gateway
            program.chat.take_event(
                _event(
                    'trigger_received',
                    desk='scalper',
                    trigger_id='t9',
                    source='user_message',
                )
            )
            await pilot.pause(0.1)
            assert len(program.screen.query(turn_view.TurnView)) == 1

        _run(scenario, tmp_path)

    def test_question_mark_opens_the_keys(self, tmp_path: Path) -> None:
        """? in the empty message box opens the keys; in a message it is typed."""

        async def scenario(program, pilot, gateway) -> None:
            """Presses ? twice.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            del gateway
            await pilot.press('question_mark')
            await pilot.pause(0.1)
            assert isinstance(program.screen, keys_screen.KeysScreen)
            await pilot.press('escape')
            await pilot.press('w', 'h', 'y', 'question_mark')
            box = program.screen.query_one(composer.Composer)
            assert box.text == 'why?'

        _run(scenario, tmp_path)

    def test_model_picker_number_key(self, tmp_path: Path) -> None:
        """Alt+P then 1 makes the desk try its first backend first."""

        async def scenario(program, pilot, gateway) -> None:
            """Chooses a model.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            del program
            await pilot.pause(0.3)
            await pilot.press('alt+p')
            await pilot.pause(0.1)
            await pilot.press('1')
            await pilot.pause(0.2)
            assert gateway.model_choices == [
                (
                    'general',
                    'claude',
                    None,
                ),
            ]

        _run(scenario, tmp_path)
