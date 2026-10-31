"""Moves the data that earlier versions wrote under the name "desk" to the name "trader".

Until the agents were renamed, each one was a desk: its folder was workspace/desks/<name>, the order book was desk_orders.db, the databases had desk columns, and the journals, sessions, cron jobs and Telegram pairings stored "desk" keys. The migration runs once, at the start of every command, and does nothing when no old data is left. Before it changes anything it copies the old data to workspace/.backups/desk-to-trader-<time>/.

Only names the code reads are changed: JSON keys, JSON values that are a single identifier such as "desk" or "flatten_desk", paths under workspace/desks/, the TradingRules.md table names, the database tables and columns, the checkpoint repositories' folder and the terminal program's remembered choice. Free text, such as a conversation or a note, is left as it was written.

Typical usage example:

  migration = TraderMigration(layout, settings_file, datetime.datetime.now())
  for change in migration.run():
      print(change)
"""

import datetime
import json
import logging
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from trading_agent.workspace import workspace_layout

_LOGGER = logging.getLogger(__name__)
_IDENTIFIER_PATTERN = re.compile(r'^[a-z_]*desk[a-z_]*$')
_RULES_TABLE_PATTERN = re.compile(r'^\[desks\.', re.MULTILINE)
_LEDGER_TABLES = (
    'ownership',
    'approvals',
    'day_owners',
)


class TraderMigration:
    """One pass over a workspace that moves its desk data to trader names.

    Attributes:
        layout: Where the workspace's files are.
        terminal_settings_file: The terminal program's remembered choices.
        now: The time that names the backup folder.
    """

    def __init__(
        self,
        layout: workspace_layout.WorkspaceLayout,
        terminal_settings_file: Path,
        now: datetime.datetime,
    ):
        """Remembers the workspace without touching it.

        Args:
            layout (workspace_layout.WorkspaceLayout): Where the workspace's files are.
            terminal_settings_file (Path): The terminal program's terminal.json.
            now (datetime.datetime): The time that names the backup folder.
        """
        self.layout = layout
        self.terminal_settings_file = terminal_settings_file
        self.now = now
        self.changes: list[str] = []

    @property
    def old_traders_directory(self) -> Path:
        """The folder that held one folder per desk."""
        return self.layout.root / 'desks'

    @property
    def old_orders_file(self) -> Path:
        """The order book's file before the rename."""
        return self.layout.shared_directory / 'desk_orders.db'

    def needed(self) -> bool:
        """Whether any data still uses the old names.

        Returns:
            bool: True when workspace/desks or desk_orders.db exists, or a database or the terminal settings still use the old names.
        """
        if self.old_traders_directory.exists():
            return True
        if self.old_orders_file.exists():
            return True
        if self._ledger_tables_to_rename():
            return True
        return self._terminal_settings_need_rename()

    def run(self) -> list[str]:
        """Backs up the old data and moves it to the trader names.

        Returns:
            list[str]: A sentence for each change made; empty when nothing needed changing.

        Raises:
            OSError: A file could not be copied, moved or written.
            sqlite3.Error: A database could not be changed.
        """
        if not self.needed():
            return []
        self._back_up()
        if self.old_traders_directory.exists():
            self._rewrite_json_files(self.old_traders_directory)
            self._rewrite_json_files(self.layout.root / 'journal')
            self._rewrite_shared_json_files()
            self._rename_rules_tables()
            self._move_trader_folders()
            self._point_checkpoints_at_trader_folders()
        self._migrate_orders_file()
        self._migrate_ledger()
        self._migrate_terminal_settings()
        for change in self.changes:
            _LOGGER.warning('Trader migration: %s', change)
        return self.changes

    def _back_up(self) -> None:
        """Copies every file the migration may change into a new backup folder.

        Returns:
            None.

        Raises:
            OSError: A file could not be copied.
        """
        stamp = self.now.strftime('%Y%m%d-%H%M%S')
        backup_directory = (
            self.layout.root / '.backups' / f'desk-to-trader-{stamp}'
        )
        backup_directory.mkdir(parents=True, exist_ok=True)
        if self.old_traders_directory.exists():
            shutil.copytree(
                self.old_traders_directory,
                backup_directory / 'desks',
                symlinks=True,
                ignore=shutil.ignore_patterns('browser_profile'),
            )
        journal_directory = self.layout.root / 'journal'
        if journal_directory.exists():
            shutil.copytree(
                journal_directory,
                backup_directory / 'journal',
                symlinks=True,
            )
        shared_backup = backup_directory / 'shared'
        shared_backup.mkdir(exist_ok=True)
        for pattern in ('*.db', '*.json', 'TradingRules.md'):
            for file in self.layout.shared_directory.glob(pattern):
                shutil.copy2(file, shared_backup / file.name)
        checkpoints_directory = self.layout.root / '.checkpoints'
        for config_file in checkpoints_directory.glob('*.git/config'):
            target = backup_directory / 'checkpoints' / config_file.parent.name
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_file, target / 'config')
        if self.terminal_settings_file.exists():
            shutil.copy2(
                self.terminal_settings_file,
                backup_directory / 'terminal.json',
            )
        self.changes.append(f'Backed up the old data to {backup_directory}')

    def _rewrite_json_files(self, directory: Path) -> None:
        """Renames the old keys and values in every JSON and JSON Lines file under a folder.

        Args:
            directory (Path): The folder to search.

        Returns:
            None.

        Raises:
            OSError: A file could not be read or written.
        """
        if not directory.exists():
            return
        rewritten = 0
        for file in sorted(directory.rglob('*')):
            if 'browser_profile' in file.parts:
                continue
            if not file.is_file() or file.is_symlink():
                continue
            changed = False
            if file.suffix == '.json':
                changed = self._rewrite_json_file(file)
            elif file.suffix == '.jsonl':
                changed = self._rewrite_json_lines_file(file)
            if changed:
                rewritten += 1
        if rewritten:
            self.changes.append(
                f'Renamed desk keys and values in {rewritten} files under {directory}'
            )

    def _rewrite_shared_json_files(self) -> None:
        """Renames the old keys and values in the JSON files directly in workspace/shared.

        Returns:
            None.

        Raises:
            OSError: A file could not be read or written.
        """
        for file in sorted(self.layout.shared_directory.glob('*.json')):
            if self._rewrite_json_file(file):
                self.changes.append(f'Renamed desk keys and values in {file}')

    def _rewrite_json_file(self, file: Path) -> bool:
        """Renames the old keys and values in one JSON file.

        Args:
            file (Path): The file.

        Returns:
            bool: True when the file was changed.

        Raises:
            OSError: The file could not be read or written.
        """
        text = file.read_text(encoding='utf-8', errors='replace')
        if 'desk' not in text:
            return False
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            return False
        renamed = self.renamed_value(document)
        if renamed == document:
            return False
        self._write_text(file, json.dumps(renamed, indent=2) + '\n')
        return True

    def _rewrite_json_lines_file(self, file: Path) -> bool:
        """Renames the old keys and values in each line of a JSON Lines file.

        A line that is not valid JSON is kept as it was.

        Args:
            file (Path): The file.

        Returns:
            bool: True when the file was changed.

        Raises:
            OSError: The file could not be read or written.
        """
        text = file.read_text(encoding='utf-8', errors='replace')
        if 'desk' not in text:
            return False
        new_lines = []
        changed = False
        for line in text.splitlines():
            if 'desk' not in line:
                new_lines.append(line)
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                new_lines.append(line)
                continue
            renamed = self.renamed_value(record)
            if renamed == record:
                new_lines.append(line)
                continue
            new_lines.append(json.dumps(renamed, ensure_ascii=False))
            changed = True
        if not changed:
            return False
        ending = ''
        if text.endswith('\n'):
            ending = '\n'
        self._write_text(file, '\n'.join(new_lines) + ending)
        return True

    def renamed_value(self, value: Any) -> Any:
        """A JSON value with its old keys, identifiers and paths renamed.

        Args:
            value (Any): A value read from JSON.

        Returns:
            Any: The same value, with each key containing "desk", each string that is a single identifier containing "desk", and each path under workspace/desks/ renamed; other text is unchanged.
        """
        if isinstance(value, dict):
            renamed_dictionary = {}
            for key, item in value.items():
                renamed_dictionary[self.renamed_word(key)] = self.renamed_value(
                    item
                )
            return renamed_dictionary
        if isinstance(value, list):
            renamed_list = []
            for item in value:
                renamed_list.append(self.renamed_value(item))
            return renamed_list
        if isinstance(value, str):
            if _IDENTIFIER_PATTERN.match(value):
                return self.renamed_word(value)
            return value.replace('workspace/desks/', 'workspace/traders/')
        return value

    @staticmethod
    def renamed_word(word: str) -> str:
        """A name with every "desk" in it changed to "trader", keeping the case.

        Args:
            word (str): The name, such as "desk_pnl" or "DeskName".

        Returns:
            str: The renamed name, such as "trader_pnl" or "TraderName".
        """
        word = word.replace('DESK', 'TRADER')
        word = word.replace('Desk', 'Trader')
        return word.replace('desk', 'trader')

    def _rename_rules_tables(self) -> None:
        """Renames the [desks.<name>] tables in TradingRules.md to [traders.<name>].

        Returns:
            None.

        Raises:
            OSError: The file could not be read or written.
        """
        rules_file = self.layout.shared_directory / 'TradingRules.md'
        if not rules_file.exists():
            return
        text = rules_file.read_text(encoding='utf-8')
        new_text = _RULES_TABLE_PATTERN.sub('[traders.', text)
        if new_text != text:
            self._write_text(rules_file, new_text)
            self.changes.append(
                f'Renamed the [desks.<name>] tables in {rules_file}'
            )

    def _move_trader_folders(self) -> None:
        """Moves workspace/desks/<name> into workspace/traders/<name>, merging with what is already there.

        A file that already exists in the trader's folder is kept, and the old one is left in workspace/desks with a warning, so nothing is overwritten.

        Returns:
            None.

        Raises:
            OSError: A file could not be moved.
        """
        new_root = self.layout.root / 'traders'
        for old_folder in sorted(self.old_traders_directory.iterdir()):
            if not old_folder.is_dir():
                continue
            self._merge_folder(old_folder, new_root / old_folder.name)
            self.changes.append(
                f'Moved {old_folder} to {new_root / old_folder.name}'
            )
        self._remove_empty_folders(self.old_traders_directory)
        if self.old_traders_directory.exists():
            self.changes.append(
                f'Left the files that already existed in workspace/traders in {self.old_traders_directory}; compare them by hand'
            )

    def _merge_folder(self, source: Path, target: Path) -> None:
        """Moves everything in one folder into another without overwriting.

        Args:
            source (Path): The folder to empty.
            target (Path): The folder to fill.

        Returns:
            None.

        Raises:
            OSError: A file could not be moved.
        """
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            return
        for child in sorted(source.iterdir()):
            target_child = target / child.name
            if not target_child.exists() and not target_child.is_symlink():
                shutil.move(str(child), str(target_child))
            elif child.is_dir() and target_child.is_dir():
                self._merge_folder(child, target_child)
            elif self._same_content(child, target_child):
                child.unlink()
            else:
                _LOGGER.warning(
                    'Trader migration kept %s and left %s in place',
                    target_child,
                    child,
                )

    @staticmethod
    def _same_content(first: Path, second: Path) -> bool:
        """Whether two paths are files with the same bytes.

        Args:
            first (Path): One path.
            second (Path): The other path.

        Returns:
            bool: True when both are regular files with equal contents.
        """
        if not first.is_file() or not second.is_file():
            return False
        return first.read_bytes() == second.read_bytes()

    def _remove_empty_folders(self, directory: Path) -> None:
        """Removes a folder and its subfolders when they hold no files.

        Args:
            directory (Path): The folder.

        Returns:
            None.
        """
        if not directory.is_dir() or directory.is_symlink():
            return
        for child in directory.iterdir():
            self._remove_empty_folders(child)
        if not any(directory.iterdir()):
            directory.rmdir()

    def _point_checkpoints_at_trader_folders(self) -> None:
        """Changes the folder recorded in each checkpoint repository's config from workspace/desks to workspace/traders.

        Returns:
            None.

        Raises:
            OSError: A config file could not be read or written.
        """
        checkpoints_directory = self.layout.root / '.checkpoints'
        for config_file in sorted(checkpoints_directory.glob('*.git/config')):
            text = config_file.read_text(encoding='utf-8')
            new_text = text.replace('/workspace/desks/', '/workspace/traders/')
            if new_text != text:
                self._write_text(config_file, new_text)
                self.changes.append(
                    f'Pointed {config_file} at the trader folder'
                )

    def _migrate_orders_file(self) -> None:
        """Renames desk_orders.db to trader_orders.db, with its table and column.

        Returns:
            None.

        Raises:
            OSError: The file could not be renamed.
            sqlite3.Error: The database could not be changed.
        """
        if not self.old_orders_file.exists():
            return
        new_file = self.layout.trader_orders_file
        if new_file.exists():
            _LOGGER.warning(
                'Trader migration left %s in place, because %s already exists',
                self.old_orders_file,
                new_file,
            )
            return
        connection = sqlite3.connect(self.old_orders_file)
        try:
            tables = self._table_names(connection)
            if 'desk_orders' in tables:
                connection.execute(
                    'ALTER TABLE desk_orders RENAME TO trader_orders'
                )
            if 'desk' in self._column_names(connection, 'trader_orders'):
                connection.execute(
                    'ALTER TABLE trader_orders RENAME COLUMN desk TO trader'
                )
            connection.commit()
        finally:
            connection.close()
        self.old_orders_file.rename(new_file)
        self.changes.append(
            f'Renamed {self.old_orders_file} to {new_file}, with its table and column'
        )

    def _ledger_tables_to_rename(self) -> list[str]:
        """The risk ledger's tables that still have a desk column.

        Returns:
            list[str]: The table names; empty when the ledger does not exist or is already migrated.

        Raises:
            sqlite3.Error: The database could not be read.
        """
        ledger_file = self.layout.risk_ledger_file
        if not ledger_file.exists():
            return []
        connection = sqlite3.connect(ledger_file)
        try:
            tables = []
            for table in _LEDGER_TABLES:
                if 'desk' in self._column_names(connection, table):
                    tables.append(table)
            return tables
        finally:
            connection.close()

    def _migrate_ledger(self) -> None:
        """Renames the desk column of the risk ledger's tables to trader.

        Returns:
            None.

        Raises:
            sqlite3.Error: The database could not be changed.
        """
        tables = self._ledger_tables_to_rename()
        if not tables:
            return
        connection = sqlite3.connect(self.layout.risk_ledger_file)
        try:
            for table in tables:
                connection.execute(
                    f'ALTER TABLE {table} RENAME COLUMN desk TO trader'
                )
            connection.commit()
        finally:
            connection.close()
        self.changes.append(
            f'Renamed the desk column of {", ".join(tables)} in {self.layout.risk_ledger_file}'
        )

    @staticmethod
    def _table_names(connection: sqlite3.Connection) -> set[str]:
        """The tables in a database.

        Args:
            connection (sqlite3.Connection): The open database.

        Returns:
            set[str]: Their names.

        Raises:
            sqlite3.Error: The database could not be read.
        """
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        names = set()
        for row in rows:
            names.add(row[0])
        return names

    @staticmethod
    def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
        """The columns of one table, or none when the table does not exist.

        Args:
            connection (sqlite3.Connection): The open database.
            table (str): The table's name, one of the names this module knows.

        Returns:
            set[str]: The column names.

        Raises:
            sqlite3.Error: The database could not be read.
        """
        rows = connection.execute(f'PRAGMA table_info({table})').fetchall()
        names = set()
        for row in rows:
            names.add(row[1])
        return names

    def _terminal_settings_need_rename(self) -> bool:
        """Whether the terminal program still remembers its choice under "desk".

        Returns:
            bool: True when terminal.json has a "desk" key and no "trader" key.
        """
        stored = self._terminal_settings()
        if stored is None:
            return False
        return 'desk' in stored and 'trader' not in stored

    def _terminal_settings(self) -> dict[str, Any] | None:
        """The terminal program's remembered choices, or None when they cannot be read.

        Returns:
            dict[str, Any] | None: The stored choices.
        """
        if not self.terminal_settings_file.exists():
            return None
        try:
            stored = json.loads(
                self.terminal_settings_file.read_text(encoding='utf-8')
            )
        except OSError, json.JSONDecodeError:
            return None
        if not isinstance(stored, dict):
            return None
        return stored

    def _migrate_terminal_settings(self) -> None:
        """Renames the terminal program's remembered "desk" to "trader".

        Returns:
            None.

        Raises:
            OSError: The file could not be written.
        """
        if not self._terminal_settings_need_rename():
            return
        stored = self._terminal_settings()
        if stored is None:
            return
        stored['trader'] = stored.pop('desk')
        self._write_text(
            self.terminal_settings_file, json.dumps(stored, indent=2) + '\n'
        )
        self.changes.append(
            f'Renamed the remembered desk in {self.terminal_settings_file}'
        )

    @staticmethod
    def _write_text(file: Path, text: str) -> None:
        """Replaces a file's text in one step, through a temporary file beside it.

        Args:
            file (Path): The file.
            text (str): Its new text.

        Returns:
            None.

        Raises:
            OSError: The file could not be written.
        """
        temporary = file.with_name(f'{file.name}.migrating')
        temporary.write_text(text, encoding='utf-8')
        temporary.replace(file)
