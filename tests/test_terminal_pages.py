"""Tests for the terminal program's pages, driven with Textual's test pilot and a stand-in gateway."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from tests import test_terminal_chat_screen as chat_tests
from trading_agent.terminal import prompt_history
from trading_agent.terminal import terminal_application
from trading_agent.terminal import terminal_settings
from trading_agent.terminal.screens import checkpoints_screen
from trading_agent.terminal.screens import files_screen
from trading_agent.terminal.screens import page_catalogue
from trading_agent.terminal.screens import trading_screen
from trading_agent.terminal.widgets import confirm_dialog


class _PagesGateway(chat_tests._StandInGateway):
    """The chat tests' stand-in gateway, with every route the pages read.

    Attributes:
        actions: The changes the pages asked for, as (route, arguments) pairs.
    """

    def __init__(self):
        """Creates the stand-in."""
        super().__init__()
        self.actions: list[tuple[str, Any]] = []

    async def journal(self, limit: int = 1500) -> dict[str, Any]:
        """No events of no desk.

        Args:
            limit (int): Ignored.

        Returns:
            dict[str, Any]: An empty journal.
        """
        del limit
        return {
            'events': [],
        }

    async def sessions(self, desk_name: str) -> dict[str, Any]:
        """One session.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The sessions document.
        """
        del desk_name
        return {
            'current': 's1',
            'sessions': [
                {
                    'session_id': 's1',
                    'exchanges': 2,
                },
            ],
        }

    async def summaries(self, desk_name: str) -> dict[str, Any]:
        """No summaries.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The summaries document.
        """
        del desk_name
        return {
            'summaries': [],
        }

    async def notes(self, desk_name: str) -> dict[str, Any]:
        """No notes.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The notes document.
        """
        del desk_name
        return {
            'notes': [],
        }

    async def files(self) -> dict[str, Any]:
        """One shared file.

        Returns:
            dict[str, Any]: The files document.
        """
        return {
            'files': [
                {
                    'name': 'User.md',
                    'desk': None,
                    'exists': True,
                    'characters': 5,
                },
            ],
        }

    async def file_text(
        self, name: str, desk_name: str | None
    ) -> dict[str, Any]:
        """The file's text.

        Args:
            name (str): The file.
            desk_name (str | None): Its desk.

        Returns:
            dict[str, Any]: The file document.
        """
        return {
            'name': name,
            'desk': desk_name,
            'text': 'hello',
        }

    async def save_file(
        self, name: str, desk_name: str | None, text: str
    ) -> dict[str, Any]:
        """Records a save.

        Args:
            name (str): The file.
            desk_name (str | None): Its desk.
            text (str): The new text.

        Returns:
            dict[str, Any]: The characters written.
        """
        self.actions.append(
            (
                'save',
                (
                    name,
                    text,
                ),
            )
        )
        return {
            'characters': len(text),
        }

    async def proposals(self) -> dict[str, Any]:
        """No proposals.

        Returns:
            dict[str, Any]: The proposals document.
        """
        return {
            'proposals': [],
        }

    async def checkpoints(self, desk_name: str) -> dict[str, Any]:
        """Two checkpoints, newest first.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The checkpoints document.
        """
        del desk_name
        return {
            'checkpoints': [
                {
                    'checkpoint_id': 'new',
                    'created_at': '2026-10-19T10:00:00+05:30',
                    'reason': 'latest',
                },
                {
                    'checkpoint_id': 'old',
                    'created_at': '2026-10-18T10:00:00+05:30',
                    'reason': 'earlier',
                },
            ],
        }

    async def jobs(self, desk_name: str) -> dict[str, Any]:
        """No jobs.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The jobs document.
        """
        del desk_name
        return {
            'jobs': [],
            'recent_runs': [],
        }

    async def alerts(self, desk_name: str) -> dict[str, Any]:
        """No alerts.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The alerts document.
        """
        del desk_name
        return {
            'alerts': [],
        }

    async def skills(self, desk_name: str) -> dict[str, Any]:
        """No skills.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The skills document.
        """
        del desk_name
        return {
            'available': [],
            'hidden': [],
        }

    async def subagents(self) -> dict[str, Any]:
        """No subagents.

        Returns:
            dict[str, Any]: The subagents document.
        """
        return {
            'subagents': [],
            'broken': [],
        }

    async def packages(self) -> dict[str, Any]:
        """No packages.

        Returns:
            dict[str, Any]: The packages document.
        """
        return {
            'packages': [],
        }

    async def usage(self) -> dict[str, Any]:
        """No usage.

        Returns:
            dict[str, Any]: The usage document.
        """
        return {
            'desks': {},
            'rate_limits': {},
        }

    async def telegram(self) -> dict[str, Any]:
        """Telegram switched off.

        Returns:
            dict[str, Any]: The Telegram status.
        """
        return {
            'enabled': False,
            'token_present': False,
            'state': 'off',
            'paired': [],
            'pending': [],
        }

    async def permission_grants(self) -> list[dict[str, Any]]:
        """No standing permissions.

        Returns:
            list[dict[str, Any]]: The grants.
        """
        return []

    async def configuration(self) -> dict[str, Any]:
        """A small configuration.

        Returns:
            dict[str, Any]: The configuration.
        """
        return {
            'mode': 'dry_run',
        }

    async def apps(self) -> list[dict[str, Any]]:
        """No apps.

        Returns:
            list[dict[str, Any]]: The apps.
        """
        return []

    async def flatten(self, desk_name: str, reason: str) -> dict[str, Any]:
        """Records a flatten.

        Args:
            desk_name (str): The desk.
            reason (str): The reason.

        Returns:
            dict[str, Any]: The flatten report.
        """
        self.actions.append(
            (
                'flatten',
                (
                    desk_name,
                    reason,
                ),
            )
        )
        return {
            'text': 'Flat.',
            'is_error': False,
        }

    async def kill(self, reason: str) -> dict[str, Any]:
        """Records the kill switch.

        Args:
            reason (str): The reason.

        Returns:
            dict[str, Any]: The kill switch report.
        """
        self.actions.append(
            (
                'kill',
                reason,
            )
        )
        return {
            'text': 'Killed.',
        }

    async def restore_checkpoint(
        self, desk_name: str, checkpoint_id: str
    ) -> dict[str, Any]:
        """Records a restore.

        Args:
            desk_name (str): The desk.
            checkpoint_id (str): The checkpoint.

        Returns:
            dict[str, Any]: The restore report.
        """
        self.actions.append(
            (
                'restore',
                checkpoint_id,
            )
        )
        return {
            'restored': checkpoint_id,
            'undo_checkpoint_id': 'undo',
        }


def _run(
    scenario: Callable[
        [terminal_application.TerminalApplication, Any, _PagesGateway],
        Awaitable[None],
    ],
    tmp_path: Path,
) -> None:
    """Runs a scenario against the program with the pages' stand-in gateway.

    Args:
        scenario (Callable[[terminal_application.TerminalApplication, Any, _PagesGateway], Awaitable[None]]): Drives the program with the pilot.
        tmp_path (Path): A folder for the settings and history.
    """
    gateway = _PagesGateway()

    async def run() -> None:
        """Starts the program, runs the scenario and stops."""
        program = terminal_application.TerminalApplication(
            gateway,
            terminal_settings.TerminalSettings(tmp_path / 'terminal.json'),
            prompt_history.PromptHistory(tmp_path / 'history'),
            'general',
        )
        async with program.run_test(size=(140, 45)) as pilot:
            await pilot.pause(0.3)
            await scenario(program, pilot, gateway)

    asyncio.run(run())


class TestPages:
    """Tests for opening the pages and their actions."""

    @pytest.mark.parametrize(
        'command',
        [page.command for page in page_catalogue.PageCatalogue().pages()],
    )
    def test_every_page_opens_and_closes(
        self, command: str, tmp_path: Path
    ) -> None:
        """Each page opens with its slash command and Escape goes back to the chat."""

        async def scenario(program, pilot, gateway) -> None:
            """Opens and closes one page.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_PagesGateway): The stand-in gateway.
            """
            del gateway
            page = page_catalogue.PageCatalogue().find(command)
            program.open_page(command)
            await pilot.pause(0.5)
            assert isinstance(program.screen, page.screen_class)
            await pilot.press('escape')
            await pilot.pause(0.1)
            assert program.screen is program.chat

        _run(scenario, tmp_path)

    def test_slash_command_opens_a_page(self, tmp_path: Path) -> None:
        """Typing /trading in the chat opens the Trading page without sending anything."""

        async def scenario(program, pilot, gateway) -> None:
            """Types /trading.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_PagesGateway): The stand-in gateway.
            """
            await pilot.press(*'/trading')
            await pilot.press('escape', 'enter')
            await pilot.pause(0.3)
            assert isinstance(program.screen, trading_screen.TradingScreen)
            assert gateway.sent == []

        _run(scenario, tmp_path)

    def test_kill_switch_needs_reason_and_word(self, tmp_path: Path) -> None:
        """The kill switch fires only with a reason and the typed word FLATTEN."""

        async def scenario(program, pilot, gateway) -> None:
            """Fires the kill switch.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_PagesGateway): The stand-in gateway.
            """
            program.open_page('/trading')
            await pilot.pause(0.4)
            await pilot.press('K')
            await pilot.pause(0.2)
            assert isinstance(program.screen, confirm_dialog.ConfirmDialog)
            await pilot.press(*'test')
            await pilot.press('enter')
            await pilot.pause(0.1)
            assert gateway.actions == []
            await pilot.press(*'flatten', 'enter')
            await pilot.pause(0.1)
            assert gateway.actions == []
            for _ in range(7):
                await pilot.press('backspace')
            await pilot.press(*'FLATTEN', 'enter')
            await pilot.pause(0.3)
            assert gateway.actions == [
                (
                    'kill',
                    'test',
                ),
            ]

        _run(scenario, tmp_path)

    def test_flatten_asks_for_a_reason(self, tmp_path: Path) -> None:
        """f on the Desks page flattens the highlighted desk with the given reason."""

        async def scenario(program, pilot, gateway) -> None:
            """Flattens the first desk.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_PagesGateway): The stand-in gateway.
            """
            program.open_page('/desks')
            await pilot.pause(0.4)
            await pilot.press('f')
            await pilot.pause(0.2)
            await pilot.press(*'done for today', 'enter')
            await pilot.pause(0.3)
            assert gateway.actions == [
                (
                    'flatten',
                    (
                        'general',
                        'done for today',
                    ),
                ),
            ]

        _run(scenario, tmp_path)

    def test_a_file_is_edited_and_saved(self, tmp_path: Path) -> None:
        """A file opens in the editor and Ctrl+S saves the changed text."""

        async def scenario(program, pilot, gateway) -> None:
            """Edits User.md.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_PagesGateway): The stand-in gateway.
            """
            program.open_page('/files')
            await pilot.pause(0.4)
            assert isinstance(program.screen, files_screen.FilesScreen)
            await pilot.press('enter')
            await pilot.pause(0.3)
            await pilot.press('end', *' world')
            await pilot.press('ctrl+s')
            await pilot.pause(0.3)
            assert gateway.actions == [
                (
                    'save',
                    (
                        'User.md',
                        'hello world',
                    ),
                ),
            ]

        _run(scenario, tmp_path)

    def test_the_newest_checkpoint_cannot_be_restored(
        self, tmp_path: Path
    ) -> None:
        """Restore refuses the newest checkpoint and restores an older one after a reason."""

        async def scenario(program, pilot, gateway) -> None:
            """Tries both checkpoints.

            Args:
                program (terminal_application.TerminalApplication): The program.
                pilot (Any): The test pilot.
                gateway (_PagesGateway): The stand-in gateway.
            """
            program.open_page('/checkpoints')
            await pilot.pause(0.4)
            assert isinstance(
                program.screen, checkpoints_screen.CheckpointsScreen
            )
            await pilot.press('s')
            await pilot.pause(0.1)
            assert not isinstance(program.screen, confirm_dialog.ConfirmDialog)
            await pilot.press('down', 's')
            await pilot.pause(0.2)
            await pilot.press(*'undo a bad note', 'enter')
            await pilot.pause(0.3)
            assert gateway.actions == [
                (
                    'restore',
                    'old',
                ),
            ]

        _run(scenario, tmp_path)
