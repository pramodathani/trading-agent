"""Snapshots of a desk's own files, so any change the desk makes can be undone.

Each desk gets its own git repository in `workspace/.checkpoints/<desk>.git`, kept apart from the project's git. Its working tree is the desk folder, but only Memory.md, memory/, notes/ and skills/agent/ are tracked; everything else in the folder is ignored. A snapshot is taken before every write the desk makes, so each checkpoint is the state just before one change.

Typical usage example:

  checkpoints = Checkpoints(Path('workspace/.checkpoints/main.git'), Path('workspace/desks/main'))
  checkpoints.snapshot('before write_file Memory.md')
  checkpoints.restore('3f2a9c1')
"""

import dataclasses
import logging
import os
import subprocess
import threading
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
TRACKED_PATHS = (
    'Memory.md',
    'memory',
    'notes',
    'skills/agent',
)
_EXCLUDE_LINES = (
    '/*',
    '!/Memory.md',
    '!/memory/',
    '!/notes/',
    '!/skills/',
    '/skills/*',
    '!/skills/agent/',
)
_FIELD_SEPARATOR = '\x1f'


class CheckpointError(RuntimeError):
    """git could not take, list or restore a checkpoint."""


@dataclasses.dataclass(frozen=True)
class Checkpoint:
    """One snapshot.

    Attributes:
        checkpoint_id: The snapshot's short git commit id.
        created_at: When it was taken, as an ISO 8601 string.
        reason: What was about to happen, such as "before write_file Memory.md".
    """

    checkpoint_id: str
    created_at: str
    reason: str


class Checkpoints:
    """The checkpoint repository of one desk.

    Attributes:
        repository_directory: The git directory that holds the snapshots.
        desk_directory: The desk folder whose files are snapshotted.
    """

    def __init__(self, repository_directory: Path, desk_directory: Path):
        """Describes the repository without touching the disk.

        Args:
            repository_directory (Path): The git directory, such as workspace/.checkpoints/main.git.
            desk_directory (Path): The desk folder.
        """
        self.repository_directory = repository_directory
        self.desk_directory = desk_directory
        self._lock = threading.Lock()

    def snapshot(self, reason: str) -> str | None:
        """Records the desk's files as they are now, if they changed since the last snapshot.

        Args:
            reason (str): What is about to happen, kept as the snapshot's message.

        Returns:
            str | None: The new checkpoint's id, or None when nothing had changed.

        Raises:
            CheckpointError: git failed.
        """
        with self._lock:
            return self._snapshot(reason)

    def list(self, limit: int = 20) -> list[Checkpoint]:
        """Lists the most recent checkpoints, newest first.

        Args:
            limit (int): The most checkpoints to list.

        Returns:
            list[Checkpoint]: The checkpoints, or an empty list when none has been taken.

        Raises:
            CheckpointError: git failed.
        """
        with self._lock:
            if not self._has_commits():
                return []
            output = self._git(
                'log',
                f'-n{limit}',
                f'--format=%h{_FIELD_SEPARATOR}%cI{_FIELD_SEPARATOR}%s',
            )
        checkpoints = []
        for line in output.splitlines():
            parts = line.split(_FIELD_SEPARATOR)
            if len(parts) != 3:
                continue
            checkpoints.append(
                Checkpoint(
                    checkpoint_id=parts[0],
                    created_at=parts[1],
                    reason=parts[2],
                )
            )
        return checkpoints

    def restore(self, checkpoint_id: str) -> str:
        """Puts the desk's files back as they were at a checkpoint.

        The current files are snapshotted first, so a restore can itself be undone. Files created after the checkpoint are removed; files outside Memory.md, memory/, notes/ and skills/agent/ are never touched.

        Args:
            checkpoint_id (str): The checkpoint to return to.

        Returns:
            str: The id of the snapshot taken just before restoring, or of the current state when nothing had changed.

        Raises:
            CheckpointError: The checkpoint does not exist, or git failed.
        """
        with self._lock:
            self._snapshot(f'before restoring {checkpoint_id}')
            try:
                self._git(
                    'rev-parse', '--verify', f'{checkpoint_id}^{{commit}}'
                )
            except CheckpointError as error:
                raise CheckpointError(
                    f'No checkpoint {checkpoint_id!r} in {self.repository_directory}'
                ) from error
            before = self._git('rev-parse', '--short', 'HEAD').strip()
            self._git(
                'restore',
                f'--source={checkpoint_id}',
                '--staged',
                '--worktree',
                '--',
                '.',
            )
            self._commit_if_changed(f'restored {checkpoint_id}')
            return before

    def _snapshot(self, reason: str) -> str | None:
        """Takes a snapshot; the caller holds the lock.

        Args:
            reason (str): The snapshot's message.

        Returns:
            str | None: The new checkpoint's id, or None when nothing had changed.
        """
        self._ensure_repository()
        return self._commit_if_changed(reason)

    def _commit_if_changed(self, message: str) -> str | None:
        """Stages every tracked change and commits it, if there is any.

        Args:
            message (str): The commit message.

        Returns:
            str | None: The new commit's short id, or None when nothing had changed.
        """
        self._git('add', '--all')
        if not self._git('status', '--porcelain').strip():
            return None
        self._git('commit', '--quiet', '--allow-empty-message', '-m', message)
        return self._git('rev-parse', '--short', 'HEAD').strip()

    def _ensure_repository(self) -> None:
        """Creates the repository the first time, and keeps its ignore rules current.

        The ignore rules are rewritten whenever they differ, so a repository created before skills/agent/ was tracked starts tracking it.
        """
        if not (self.repository_directory / 'HEAD').is_file():
            self.repository_directory.parent.mkdir(parents=True, exist_ok=True)
            self.desk_directory.mkdir(parents=True, exist_ok=True)
            self._git('init', '--quiet')
        exclude_file = self.repository_directory / 'info' / 'exclude'
        wanted = '\n'.join(_EXCLUDE_LINES) + '\n'
        current = ''
        if exclude_file.is_file():
            current = exclude_file.read_text(encoding='utf-8')
        if current == wanted:
            return
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        exclude_file.write_text(wanted, encoding='utf-8')

    def _has_commits(self) -> bool:
        """Says whether any snapshot has been taken.

        Returns:
            bool: True when the repository exists and has at least one commit.
        """
        if not (self.repository_directory / 'HEAD').is_file():
            return False
        try:
            self._git('rev-parse', '--verify', 'HEAD')
        except CheckpointError:
            return False
        return True

    def _git(self, *arguments: str) -> str:
        """Runs one git command against the checkpoint repository.

        The user's global and system git settings are ignored, so a setting such as commit signing or a hook cannot break or slow down a snapshot.

        Args:
            *arguments (str): The git subcommand and its arguments.

        Returns:
            str: What git printed.

        Raises:
            CheckpointError: git is missing or reported an error.
        """
        environment = dict(os.environ)
        environment['GIT_CONFIG_GLOBAL'] = os.devnull
        environment['GIT_CONFIG_NOSYSTEM'] = '1'
        command = [
            'git',
            f'--git-dir={self.repository_directory.resolve()}',
            f'--work-tree={self.desk_directory.resolve()}',
            '-c',
            'user.name=trading-agent',
            '-c',
            'user.email=trading-agent@localhost',
            '-c',
            'commit.gpgsign=false',
            *arguments,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=self.desk_directory,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise CheckpointError(f'Could not run git: {error}') from error
        if completed.returncode != 0:
            raise CheckpointError(
                f'git {arguments[0]} failed: {completed.stderr.strip()}'
            )
        return completed.stdout
