"""Builds the bwrap command line that runs the agent's bash terminal in a sandbox.

Inside the sandbox the whole filesystem is visible but read-only, except the trader's scratch folder and a private /tmp. Files that hold secrets are replaced by empty ones, the environment starts empty, and the sandbox has its own process list, so it cannot see or signal the gateway. The network is shared, so the agent can reach the internet; the local databases and UBI it can reach all require credentials that are hidden.

Typical usage example:

  sandbox = BashSandbox(scratch_directory, hidden_paths)
  argument_list = sandbox.command(['bash', '--noprofile', '--norc'])
"""

import glob
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

_SANDBOX_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'


class BashSandbox:
    """The sandbox for one trader's terminal.

    Attributes:
        scratch_directory: The only folder of the real filesystem the sandbox can write to.
        home_directory: The sandbox's HOME, inside the scratch folder.
    """

    def __init__(
        self,
        scratch_directory: Path,
        hidden_path_patterns: Sequence[str],
        passed_variable_names: Sequence[str] = (),
    ):
        """Describes the sandbox without starting anything.

        Args:
            scratch_directory (Path): The trader's scratch folder.
            hidden_path_patterns (Sequence[str]): Files and folders to hide; "~" and "*" are expanded.
            passed_variable_names (Sequence[str]): Environment variables the user chose to pass from the gateway into the sandbox, such as an API key a skill's script needs.
        """
        self.scratch_directory = scratch_directory.resolve()
        self.home_directory = self.scratch_directory / 'home'
        self._hidden_path_patterns = list(hidden_path_patterns)
        self._passed_variable_names = list(passed_variable_names)

    def passed_environment(self) -> dict[str, str]:
        """The environment variables passed into the sandbox that are set in the gateway.

        Returns:
            dict[str, str]: Each passed variable that has a value, with that value.
        """
        environment = {}
        for name in self._passed_variable_names:
            value = os.environ.get(name)
            if value:
                environment[name] = value
        return environment

    def hidden_paths(self) -> list[Path]:
        """Expands the hidden path patterns into the paths that exist now.

        Each path is resolved to where it really is, because a link such as /var/run pointing at /run would otherwise hide the same file twice, which bwrap refuses. A path inside a folder that is already hidden is left out, because the folder's empty replacement no longer contains it.

        Returns:
            list[Path]: Every existing file and folder to hide, outermost first.
        """
        resolved = set()
        for pattern in self._hidden_path_patterns:
            expanded = os.path.expanduser(pattern)
            for match in glob.glob(expanded):
                resolved.add(Path(match).resolve())
        kept = []
        for path in sorted(
            resolved, key=lambda candidate: len(candidate.parts)
        ):
            inside_hidden_folder = False
            for outer in kept:
                if path != outer and path.is_relative_to(outer):
                    inside_hidden_folder = True
            if not inside_hidden_folder:
                kept.append(path)
        return kept

    def command(self, program: Sequence[str]) -> list[str]:
        """Builds the full command line that runs a program inside the sandbox.

        Args:
            program (Sequence[str]): The program and its arguments.

        Returns:
            list[str]: The bwrap command line.

        Raises:
            FileNotFoundError: bwrap is not installed.
        """
        bwrap_path = shutil.which('bwrap')
        if bwrap_path is None:
            raise FileNotFoundError(
                'bwrap is not installed; run: sudo apt install bubblewrap'
            )
        self.home_directory.mkdir(parents=True, exist_ok=True)
        arguments = [
            bwrap_path,
            '--ro-bind',
            '/',
            '/',
            '--dev',
            '/dev',
            '--proc',
            '/proc',
            '--tmpfs',
            '/tmp',
        ]
        for path in self.hidden_paths():
            arguments.extend(self._hiding_arguments(path))
        arguments.extend(
            [
                '--bind',
                str(self.scratch_directory),
                str(self.scratch_directory),
                '--unshare-pid',
                '--unshare-ipc',
                '--unshare-uts',
                '--die-with-parent',
                '--new-session',
                '--clearenv',
                '--setenv',
                'PATH',
                self._path_variable(),
                '--setenv',
                'HOME',
                str(self.home_directory),
                '--setenv',
                'LANG',
                'C.UTF-8',
                '--setenv',
                'TERM',
                'dumb',
                '--chdir',
                str(self.scratch_directory),
            ]
        )
        for name, value in self.passed_environment().items():
            arguments.extend(
                [
                    '--setenv',
                    name,
                    value,
                ]
            )
        arguments.extend(program)
        return arguments

    def _hiding_arguments(self, path: Path) -> list[str]:
        """The bwrap arguments that hide one path.

        A folder is covered by an empty in-memory folder, and a file or socket by the empty /dev/null.

        Args:
            path (Path): The path to hide.

        Returns:
            list[str]: The arguments.
        """
        if path.is_dir() and not path.is_symlink():
            return [
                '--tmpfs',
                str(path),
            ]
        return [
            '--ro-bind',
            '/dev/null',
            str(path),
        ]

    def _path_variable(self) -> str:
        """The PATH inside the sandbox: the system folders plus the user's own bin folders.

        Returns:
            str: The PATH value.
        """
        extra = []
        for candidate in [
            Path.home() / '.local' / 'bin',
            Path(os.path.dirname(shutil.which('node') or '')),
        ]:
            if str(candidate) not in ('', '.') and candidate.is_dir():
                extra.append(str(candidate))
        return ':'.join([*extra, _SANDBOX_PATH])
