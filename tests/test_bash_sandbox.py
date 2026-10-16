"""Tests for the bash sandbox and terminal, run against the real bwrap."""

import asyncio
import os
import shutil
from pathlib import Path

import pytest

from trading_agent.tools import bash_sandbox
from trading_agent.tools import bash_session

pytestmark = pytest.mark.skipif(
    shutil.which('bwrap') is None,
    reason='bwrap is not installed',
)


class _Folders:
    """A scratch folder, a secret file and a folder outside the sandbox's write access.

    Attributes:
        scratch: The sandbox's writable folder.
        secret: A file the sandbox must not read.
        outside: A folder the sandbox must not write to.
    """

    def __init__(self, tmp_path: Path):
        """Creates the folders and files.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        self.scratch = tmp_path / 'scratch'
        self.scratch.mkdir()
        self.secret = tmp_path / 'secret.env'
        self.secret.write_text('API_KEY=do-not-leak', encoding='utf-8')
        self.outside = tmp_path / 'outside'
        self.outside.mkdir()

    def session(
        self, timeout_seconds: float = 10.0
    ) -> bash_session.BashSession:
        """Builds a terminal whose sandbox hides the secret file.

        Args:
            timeout_seconds (float): How long one command may run.

        Returns:
            bash_session.BashSession: The terminal, not started yet.
        """
        sandbox = bash_sandbox.BashSandbox(
            self.scratch,
            [
                str(self.secret),
            ],
        )
        return bash_session.BashSession(sandbox, timeout_seconds, 4000)


def _run_all(
    session: bash_session.BashSession,
    commands: list[str],
) -> list[bash_session.CommandOutcome]:
    """Runs commands one after another in one terminal, then closes it.

    Args:
        session (bash_session.BashSession): The terminal.
        commands (list[str]): The commands.

    Returns:
        list[bash_session.CommandOutcome]: Each command's outcome.
    """

    async def scenario() -> list[bash_session.CommandOutcome]:
        """Runs the commands.

        Returns:
            list[bash_session.CommandOutcome]: The outcomes.
        """
        outcomes = []
        for command in commands:
            outcomes.append(await session.run(command))
        await session.close()
        return outcomes

    return asyncio.run(scenario())


class TestBashSandbox:
    """Tests that the sandbox keeps the terminal away from secrets and the user's files."""

    def test_hidden_file_cannot_be_read(self, tmp_path: Path) -> None:
        """The secret file's contents are not visible inside the sandbox.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        folders = _Folders(tmp_path)

        outcome = _run_all(folders.session(), [f'cat {folders.secret}'])[0]

        assert 'do-not-leak' not in outcome.output

    def test_gateway_environment_does_not_reach_the_terminal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A secret in the gateway's environment is not in the terminal's environment.

        Args:
            tmp_path (Path): A temporary folder from pytest.
            monkeypatch (pytest.MonkeyPatch): Sets the variable for this test only.
        """
        monkeypatch.setenv('TRADING_AGENT_GATEWAY_ACCESS_TOKEN', 'secret-token')
        folders = _Folders(tmp_path)

        outcome = _run_all(folders.session(), ['env'])[0]

        assert 'secret-token' not in outcome.output
        assert (
            os.environ['TRADING_AGENT_GATEWAY_ACCESS_TOKEN'] == 'secret-token'
        )

    def test_only_scratch_is_writable(self, tmp_path: Path) -> None:
        """Writing inside scratch works; writing outside it fails and leaves nothing behind.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        folders = _Folders(tmp_path)

        outcomes = _run_all(
            folders.session(),
            [
                'echo kept > note.txt',
                f'echo leaked > {folders.outside}/note.txt',
            ],
        )

        assert outcomes[0].exit_status == 0
        assert (folders.scratch / 'note.txt').read_text() == 'kept\n'
        assert outcomes[1].exit_status != 0
        assert not (folders.outside / 'note.txt').exists()

    def test_folder_and_variables_carry_over(self, tmp_path: Path) -> None:
        """A cd and an export in one command still apply in the next.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        folders = _Folders(tmp_path)

        outcomes = _run_all(
            folders.session(),
            [
                'mkdir -p work && cd work && export NOTE=kept',
                'basename "$PWD"; echo "$NOTE"',
            ],
        )

        assert outcomes[1].output == 'work\nkept'

    def test_command_waiting_for_input_does_not_hang(
        self, tmp_path: Path
    ) -> None:
        """A command that reads the keyboard gets end-of-input at once.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        folders = _Folders(tmp_path)

        outcome = _run_all(folders.session(), ['cat; echo done'])[0]

        assert outcome.output == 'done'

    def test_slow_command_restarts_the_terminal(self, tmp_path: Path) -> None:
        """A command past the time limit is stopped and the next command gets a fresh terminal.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        folders = _Folders(tmp_path)

        outcomes = _run_all(
            folders.session(timeout_seconds=1.0),
            [
                'export NOTE=kept',
                'sleep 5',
                'echo "note=$NOTE"',
            ],
        )

        assert outcomes[1].exit_status is None
        assert 'did not finish' in outcomes[1].output
        assert outcomes[2].output == 'note='

    def test_exit_status_is_reported(self, tmp_path: Path) -> None:
        """A failing command's exit status comes back.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        folders = _Folders(tmp_path)

        outcome = _run_all(
            folders.session(), ['exit_with() { return "$1"; }; exit_with 3']
        )[0]

        assert outcome.exit_status == 3

    def test_background_job_runs_and_finishes(self, tmp_path: Path) -> None:
        """A background job reports running at first and finished with its output later.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        folders = _Folders(tmp_path)
        session = folders.session()

        async def scenario() -> tuple[str, str]:
            """Starts a short job and checks it twice.

            Returns:
                tuple[str, str]: The first and second check's output.
            """
            job_id = await session.run_in_background(
                'sleep 1; echo finished-work'
            )
            first = await session.check_background(job_id)
            await asyncio.sleep(2)
            second = await session.check_background(job_id)
            await session.close()
            return first.output, second.output

        first, second = asyncio.run(scenario())

        assert first.startswith('running')
        assert second == 'finished\nfinished-work'

    def test_linked_path_is_hidden_once(self, tmp_path: Path) -> None:
        """Two names for the same file, through a link, become one hidden path.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        real = tmp_path / 'real'
        real.mkdir()
        (real / 'secret').write_text('x', encoding='utf-8')
        (tmp_path / 'link').symlink_to(real)
        sandbox = bash_sandbox.BashSandbox(
            tmp_path,
            [
                str(real / 'secret'),
                str(tmp_path / 'link' / 'secret'),
            ],
        )

        assert sandbox.hidden_paths() == [
            (real / 'secret').resolve(),
        ]

    def test_path_inside_hidden_folder_is_left_out(
        self, tmp_path: Path
    ) -> None:
        """A file inside a hidden folder is not hidden separately.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        folder = tmp_path / 'broker'
        folder.mkdir()
        (folder / '.env').write_text('x', encoding='utf-8')
        sandbox = bash_sandbox.BashSandbox(
            tmp_path,
            [
                str(folder / '.env'),
                str(folder),
            ],
        )

        assert sandbox.hidden_paths() == [
            folder.resolve(),
        ]
