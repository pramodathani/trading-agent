"""Tests for the terminal program's chat screen, driven with Textual's test pilot and a stand-in gateway."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from textual import events

from trading_agent.terminal import attachable_files
from trading_agent.terminal import gateway_client
from trading_agent.terminal import prompt_history
from trading_agent.terminal import terminal_application
from trading_agent.terminal import terminal_settings
from trading_agent.terminal.widgets import command_menu
from trading_agent.terminal.widgets import composer
from trading_agent.terminal.widgets import funds_card
from trading_agent.terminal.widgets import keys_screen
from trading_agent.terminal.widgets import orders_card
from trading_agent.terminal.widgets import permission_card
from trading_agent.terminal.widgets import progress_line
from trading_agent.terminal.widgets import side_panel
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
        self.pending: list[dict[str, Any]] = []
        self.decisions: list[tuple[str, str, Any]] = []
        self.sent_attachments: list[list[str]] = []

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
            attachment_ids (Any): The uploads sent with it.

        Returns:
            str: A trigger id.
        """
        self.sent.append(
            (
                desk_name,
                text,
            )
        )
        self.sent_attachments.append(list(attachment_ids))
        return f'sent-{len(self.sent)}'

    async def upload_attachment(
        self, desk_name: str, file_path: Path
    ) -> dict[str, Any]:
        """Pretends to upload a file.

        Args:
            desk_name (str): The desk.
            file_path (Path): The file.

        Returns:
            dict[str, Any]: An attachment named after the file.
        """
        return {
            'attachment_id': f'upload-{file_path.name}',
            'desk': desk_name,
            'kind': 'document',
            'file_name': file_path.name,
            'problem': None,
        }

    async def account(self) -> dict[str, Any]:
        """An account with a balance and some margin in use.

        Returns:
            dict[str, Any]: The account.
        """
        return {
            'total_balance': 123456.7,
            'margin_utilized': 23456.7,
            'day_pnl': 1250.0,
            'week_pnl': -300.0,
            'desk_pnl': {
                'general': 1250.0,
            },
            'positions': [],
            'holdings': {},
            'owners': [],
            'halts': [],
        }

    async def desk_orders(self) -> dict[str, Any]:
        """One open order on the general desk.

        Returns:
            dict[str, Any]: The open orders by desk.
        """
        return {
            'general': [
                {
                    'order_id': 'o1',
                },
            ],
        }

    async def desk_context(self, desk_name: str) -> dict[str, Any]:
        """A small context window snapshot.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The context document.
        """
        return {
            'desk': desk_name,
            'usage': {
                'backend': 'claude',
                'model': 'claude-opus-5-5',
                'total_tokens': 1000,
                'context_window': 10000,
                'categories': [
                    {
                        'name': 'Messages',
                        'tokens': 1000,
                        'deferred': False,
                    },
                ],
                'measured': True,
                'recorded_at': '2026-10-19T04:30:00+00:00',
            },
            'tools': [
                'get_quote',
            ],
        }

    async def mcp_servers(self) -> dict[str, Any]:
        """No MCP servers.

        Returns:
            dict[str, Any]: The servers document.
        """
        return {
            'servers': [],
        }

    async def requests(self, status: str = 'pending') -> list[dict[str, Any]]:
        """The pending requests set by the test.

        Args:
            status (str): Ignored.

        Returns:
            list[dict[str, Any]]: The requests.
        """
        del status
        return list(self.pending)

    async def answer_questions(
        self, request_id: str, answers: Any
    ) -> dict[str, Any]:
        """Records answers and clears the request.

        Args:
            request_id (str): The request.
            answers (Any): The answers.

        Returns:
            dict[str, Any]: An empty request.
        """
        return self._decided(request_id, 'answer', list(answers))

    async def decide_plan(
        self, request_id: str, decision: str, feedback: str
    ) -> dict[str, Any]:
        """Records a plan decision and clears the request.

        Args:
            request_id (str): The request.
            decision (str): The decision.
            feedback (str): The feedback.

        Returns:
            dict[str, Any]: An empty request.
        """
        return self._decided(
            request_id,
            decision,
            feedback,
        )

    async def decide_permission(
        self, request_id: str, decision: str, reason: str
    ) -> dict[str, Any]:
        """Records a permission decision and clears the request.

        Args:
            request_id (str): The request.
            decision (str): The decision.
            reason (str): The reason.

        Returns:
            dict[str, Any]: An empty request.
        """
        return self._decided(request_id, decision, reason)

    def _decided(
        self, request_id: str, decision: str, detail: Any
    ) -> dict[str, Any]:
        """Records a decision and removes the request from the pending ones.

        Args:
            request_id (str): The request.
            decision (str): The decision.
            detail (Any): The answers, feedback or reason.

        Returns:
            dict[str, Any]: An empty request.
        """
        self.decisions.append(
            (
                request_id,
                decision,
                detail,
            )
        )
        remaining = []
        for request in self.pending:
            if request['request_id'] != request_id:
                remaining.append(request)
        self.pending = remaining
        return {}

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


def _permission_request() -> dict[str, Any]:
    """A pending permission request for flatten_desk on the general desk.

    Returns:
        dict[str, Any]: The request.
    """
    return {
        'request_id': 'r1',
        'desk': 'general',
        'kind': 'permission',
        'status': 'pending',
        'content': {
            'tool_name': 'flatten_desk',
            'arguments': {
                'reason': 'test',
            },
        },
        'expires_at': '2099-01-01T00:00:00+00:00',
    }


class TestRequestDock:
    """Tests for answering the desk's requests from the dock."""

    def test_a_request_never_takes_the_focus(self, tmp_path: Path) -> None:
        """A new request appears without moving the focus, so Enter still sends the typed message."""

        async def scenario(program, pilot, gateway) -> None:
            """Types, lets a request arrive, presses Enter.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            await pilot.press(*'hello')
            gateway.pending = [
                _permission_request(),
            ]
            program.chat.refresh_requests()
            await pilot.pause(0.3)
            assert program.screen.query(permission_card.PermissionCard)
            await pilot.press('enter')
            await pilot.pause(0.2)
            assert gateway.decisions == []
            assert gateway.sent[-1] == (
                'general',
                'hello',
            )

        _run(scenario, tmp_path)

    def test_a_typed_reason_denies(self, tmp_path: Path) -> None:
        """Tab reaches the card; letters go to the reason box; Enter there denies with the reason."""

        async def scenario(program, pilot, gateway) -> None:
            """Denies a permission request with a reason.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            gateway.pending = [
                _permission_request(),
            ]
            program.chat.refresh_requests()
            await pilot.pause(0.3)
            await pilot.press('tab')
            await pilot.press(*'not now')
            await pilot.press('enter')
            await pilot.pause(0.3)
            assert gateway.decisions == [
                (
                    'r1',
                    'deny',
                    'not now',
                ),
            ]
            assert not program.screen.query(permission_card.PermissionCard)

        _run(scenario, tmp_path)

    def test_number_keys_decide_permission(self, tmp_path: Path) -> None:
        """2 on the card allows the tool from now on."""

        async def scenario(program, pilot, gateway) -> None:
            """Allows a tool always.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            gateway.pending = [
                _permission_request(),
            ]
            program.chat.refresh_requests()
            await pilot.pause(0.3)
            await pilot.press('tab', '2')
            await pilot.pause(0.3)
            assert gateway.decisions[0][1] == 'always_allow'

        _run(scenario, tmp_path)

    def test_keep_planning_needs_feedback(self, tmp_path: Path) -> None:
        """Keep planning without feedback is refused on the card; with feedback it is sent."""

        async def scenario(program, pilot, gateway) -> None:
            """Sends a plan back.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            gateway.pending = [
                {
                    'request_id': 'p1',
                    'desk': 'general',
                    'kind': 'plan',
                    'status': 'pending',
                    'content': {
                        'title': 'A plan',
                        'plan': '1. Wait.',
                    },
                },
            ]
            program.chat.refresh_requests()
            await pilot.pause(0.3)
            await pilot.press('tab', '2')
            await pilot.pause(0.2)
            assert gateway.decisions == []
            await pilot.press(*'shorter')
            await pilot.press('enter')
            await pilot.pause(0.3)
            assert gateway.decisions == [
                (
                    'p1',
                    'revise',
                    'shorter',
                ),
            ]

        _run(scenario, tmp_path)

    def test_a_single_question_is_answered_by_its_number(
        self, tmp_path: Path
    ) -> None:
        """For one single-choice question, its option number sends the answer at once."""

        async def scenario(program, pilot, gateway) -> None:
            """Answers a question.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            gateway.pending = [
                {
                    'request_id': 'q1',
                    'desk': 'general',
                    'kind': 'question',
                    'status': 'pending',
                    'content': {
                        'questions': [
                            {
                                'question': 'Which?',
                                'header': 'Pick',
                                'multi_select': False,
                                'options': [
                                    {
                                        'label': 'Red',
                                        'description': 'red',
                                    },
                                    {
                                        'label': 'Blue',
                                        'description': 'blue',
                                    },
                                ],
                            },
                        ],
                    },
                },
            ]
            program.chat.refresh_requests()
            await pilot.pause(0.3)
            await pilot.press('tab', '2')
            await pilot.pause(0.3)
            assert gateway.decisions == [
                (
                    'q1',
                    'answer',
                    [
                        {
                            'selected': [
                                'Blue',
                            ],
                            'other': '',
                        },
                    ],
                ),
            ]

        _run(scenario, tmp_path)


class TestSidePanel:
    """Tests for the side panel."""

    def test_cards_show_the_account(self, tmp_path: Path) -> None:
        """The Funds card shows the balance in Indian grouping, and the Orders card counts the open order."""

        async def scenario(program, pilot, gateway) -> None:
            """Reads the cards.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            del gateway
            await pilot.pause(0.5)
            funds = program.screen.query_one(funds_card.FundsCard)
            assert '₹1,23,456.70' in str(funds.query_one('.side-body').render())
            orders = program.screen.query_one(orders_card.OrdersCard)
            body = str(orders.query_one('.side-body').render())
            assert 'Open orders' in body
            assert body.splitlines()[3].endswith('1')

        _run(scenario, tmp_path)

    def test_ctrl_b_hides_the_panel_and_remembers(self, tmp_path: Path) -> None:
        """Ctrl+B hides the panel and saves the choice."""

        async def scenario(program, pilot, gateway) -> None:
            """Toggles the panel.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            del gateway
            panel = program.screen.query_one(side_panel.SidePanel)
            assert panel.display
            await pilot.press('ctrl+b')
            assert not panel.display
            saved = terminal_settings.TerminalSettings.load(
                tmp_path / 'terminal.json'
            )
            assert not saved.side_panel_open

        _run(scenario, tmp_path)

    def test_a_folded_card_is_remembered(self, tmp_path: Path) -> None:
        """Folding a card saves its name among the folded cards."""

        async def scenario(program, pilot, gateway) -> None:
            """Folds the Funds card.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            del gateway
            program.screen.query_one(funds_card.FundsCard).collapsed = True
            await pilot.pause(0.2)
            saved = terminal_settings.TerminalSettings.load(
                tmp_path / 'terminal.json'
            )
            assert saved.collapsed_cards == [
                'funds',
            ]

        _run(scenario, tmp_path)


class TestOrdersCard:
    """Tests for the counts of the Orders card."""

    def test_counts_come_from_the_events(self) -> None:
        """Placed and cancelled orders and fills with a quantity are counted; a zero fill is not a trade."""
        card = orders_card.OrdersCard()
        events = [
            _event('order', action='placed'),
            _event('order', action='placed'),
            _event('order', action='cancelled'),
            _event('fill', filled_quantity=10),
            _event('fill', filled_quantity=0),
        ]
        captured = []
        card.show_body = captured.append

        card.show('general', events, [], None)

        lines = captured[0].plain.splitlines()
        assert lines[0].endswith('2')
        assert lines[1].endswith('1')
        assert lines[2].endswith('1')
        assert lines[4].endswith('—')


class TestAttachments:
    """Tests for attaching files to a message."""

    def test_an_at_path_is_uploaded_and_sent(self, tmp_path: Path) -> None:
        """@path names a file that is uploaded and sent with the message, without the @ word."""
        note = tmp_path / 'note.txt'
        note.write_text('hello', encoding='utf-8')

        async def scenario(program, pilot, gateway) -> None:
            """Sends a message with an @path.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            box = program.screen.query_one(composer.Composer)
            box.set_text(f'@{note} read this')
            await pilot.press('escape')
            await pilot.press('enter')
            await pilot.pause(0.5)
            assert gateway.sent[-1] == (
                'general',
                'read this',
            )
            assert gateway.sent_attachments[-1] == [
                'upload-note.txt',
            ]

        _run(scenario, tmp_path)

    def test_a_dropped_file_waits_for_the_next_message(
        self, tmp_path: Path
    ) -> None:
        """A pasted file path is attached, not typed, and goes with the next message."""
        chart = tmp_path / 'chart one.csv'
        chart.write_text('a,b', encoding='utf-8')

        async def scenario(program, pilot, gateway) -> None:
            """Drops a file, then sends.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_StandInGateway): The stand-in gateway.
            """
            box = program.screen.query_one(composer.Composer)
            box.post_message(events.Paste(f"'{chart}'"))
            await pilot.pause(0.3)
            assert box.text == ''
            await pilot.press(*'see file')
            await pilot.press('enter')
            await pilot.pause(0.5)
            assert gateway.sent_attachments[-1] == [
                'upload-chart one.csv',
            ]

        _run(scenario, tmp_path)


class TestAttachableFiles:
    """Tests for the rules and forms of attachable files."""

    def test_pasted_forms(self, tmp_path: Path) -> None:
        """Quoted paths, escaped spaces and file:// addresses are all read; other text is not."""
        picture = tmp_path / 'a b.png'
        picture.write_bytes(b'x')
        files = attachable_files.AttachableFiles()

        assert files.from_paste(f"'{picture}'") == [
            picture,
        ]
        assert files.from_paste(str(picture).replace(' ', '\\ ')) == [
            picture,
        ]
        assert files.from_paste(
            f'file://{str(picture).replace(" ", "%20")}'
        ) == [
            picture,
        ]
        assert files.from_paste('just some words') == []

    def test_problems(self, tmp_path: Path) -> None:
        """A file of an unknown kind is refused with a reason."""
        program = tmp_path / 'tool.exe'
        program.write_bytes(b'x')
        report = tmp_path / 'report.pdf'
        report.write_bytes(b'x')
        files = attachable_files.AttachableFiles()

        assert 'not a picture or document' in files.problem(program)
        assert files.problem(report) is None

    def test_suggestions(self, tmp_path: Path) -> None:
        """Suggestions list attachable files and folders that start with the typed name."""
        (tmp_path / 'charts').mkdir()
        (tmp_path / 'chart.png').write_bytes(b'x')
        (tmp_path / 'chat.exe').write_bytes(b'x')
        files = attachable_files.AttachableFiles()

        assert files.suggestions(f'{tmp_path}/cha') == [
            f'{tmp_path}/chart.png',
            f'{tmp_path}/charts/',
        ]
