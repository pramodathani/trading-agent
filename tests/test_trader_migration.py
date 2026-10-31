"""Tests for moving data written under the name "desk" to the name "trader"."""

import datetime
import json
import sqlite3
from pathlib import Path

from trading_agent.workspace import trader_migration
from trading_agent.workspace import workspace_layout

_OLD_LEDGER_SCHEMA = (
    'CREATE TABLE ownership (instrument_id TEXT PRIMARY KEY, desk TEXT NOT NULL, claimed_at TEXT NOT NULL)',
    'CREATE TABLE approvals (desk TEXT NOT NULL, approved_at TEXT NOT NULL)',
    'CREATE TABLE day_owners (trading_date TEXT NOT NULL, instrument_id TEXT NOT NULL, desk TEXT NOT NULL, PRIMARY KEY (trading_date, instrument_id))',
)


class _OldWorkspace:
    """A workspace as an earlier version left it, with desks."""

    def __init__(self, tmp_path: Path):
        """Writes the old files into a temporary folder.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        self.root = tmp_path / 'workspace'
        self.layout = workspace_layout.WorkspaceLayout(self.root)
        self.terminal_file = tmp_path / 'state' / 'terminal.json'
        self._write_trader_folder()
        self._write_shared_files()
        self._write_databases()
        self._write_terminal_settings()

    def _write_trader_folder(self) -> None:
        """Writes one desk's folder, its journal and its checkpoint config.

        Returns:
            None.
        """
        desk = self.root / 'desks' / 'scalper'
        (desk / 'journal').mkdir(parents=True)
        (desk / 'cron').mkdir()
        (desk / 'Memory.md').write_text(
            'The scalper desk keeps its stops tight.\n', encoding='utf-8'
        )
        event = {
            'kind': 'desk_started',
            'desk': 'scalper',
            'data': {
                'desk_pnl': 12.5,
                'tool_name': 'flatten_desk',
                'text': 'The desk is flat.',
                'path': 'workspace/desks/scalper/uploads/a.png',
            },
        }
        (desk / 'journal' / '2026-10-20.jsonl').write_text(
            json.dumps(event) + '\nnot json but mentions desk\n',
            encoding='utf-8',
        )
        (desk / 'cron' / 'jobs.json').write_text(
            json.dumps(
                [
                    {
                        'target': 'desk',
                        'instructions': 'Check the desk.',
                    },
                ]
            ),
            encoding='utf-8',
        )
        new_desk = self.root / 'traders' / 'scalper'
        new_desk.mkdir(parents=True)
        (new_desk / 'Persona.md').write_text('Persona\n', encoding='utf-8')
        journal = self.root / 'journal'
        journal.mkdir()
        (journal / '2026-10-20.jsonl').write_text(
            json.dumps(
                {
                    'kind': 'error',
                    'desk': None,
                }
            )
            + '\n',
            encoding='utf-8',
        )
        repository = self.root / '.checkpoints' / 'scalper.git'
        repository.mkdir(parents=True)
        (repository / 'config').write_text(
            f'[core]\n\tworktree = {self.root}/desks/scalper\n',
            encoding='utf-8',
        )

    def _write_shared_files(self) -> None:
        """Writes the Telegram pairing and TradingRules.md.

        Returns:
            None.
        """
        shared = self.layout.shared_directory
        shared.mkdir(parents=True)
        (shared / 'telegram_pairing.json').write_text(
            json.dumps(
                {
                    'paired': [
                        {
                            'chat_id': 1,
                            'desk': 'general',
                        },
                    ],
                    'pending': [],
                }
            ),
            encoding='utf-8',
        )
        (shared / 'TradingRules.md').write_text(
            '```toml limits\n[account]\n\n[desks.scalper]\nallowed_products = ["mis"]\n```\nEach desk follows these.\n',
            encoding='utf-8',
        )

    def _write_databases(self) -> None:
        """Writes the old order book and risk ledger.

        Returns:
            None.
        """
        orders = sqlite3.connect(
            self.layout.shared_directory / 'desk_orders.db'
        )
        orders.execute(
            'CREATE TABLE desk_orders (record_id TEXT PRIMARY KEY, desk TEXT NOT NULL)'
        )
        orders.execute("INSERT INTO desk_orders VALUES ('r1', 'scalper')")
        orders.commit()
        orders.close()
        ledger = sqlite3.connect(self.layout.risk_ledger_file)
        for statement in _OLD_LEDGER_SCHEMA:
            ledger.execute(statement)
        ledger.execute(
            "INSERT INTO ownership VALUES ('NSE:1', 'scalper', 'now')"
        )
        ledger.commit()
        ledger.close()

    def _write_terminal_settings(self) -> None:
        """Writes the terminal program's remembered desk.

        Returns:
            None.
        """
        self.terminal_file.parent.mkdir(parents=True)
        self.terminal_file.write_text(
            json.dumps(
                {
                    'desk': 'scalper',
                    'theme': 'dark',
                }
            ),
            encoding='utf-8',
        )

    def migration(self) -> trader_migration.TraderMigration:
        """A migration over this workspace.

        Returns:
            trader_migration.TraderMigration: The migration, at a fixed time.
        """
        return trader_migration.TraderMigration(
            self.layout,
            self.terminal_file,
            datetime.datetime(2026, 11, 1, 9, 0, 0, tzinfo=datetime.UTC),
        )


class TestTraderMigration:
    """Tests for the migration from desks to traders."""

    def test_trader_folder_is_moved_and_merged(self, tmp_path: Path) -> None:
        """The desk's files join the trader's folder, which keeps its own files.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            None.
        """
        workspace = _OldWorkspace(tmp_path)
        workspace.migration().run()
        trader = workspace.root / 'traders' / 'scalper'
        assert not (workspace.root / 'desks').exists()
        assert (trader / 'Persona.md').read_text(encoding='utf-8') == (
            'Persona\n'
        )
        assert (trader / 'Memory.md').read_text(encoding='utf-8') == (
            'The scalper desk keeps its stops tight.\n'
        )

    def test_journal_keys_and_identifiers_are_renamed(
        self, tmp_path: Path
    ) -> None:
        """Keys, identifiers and paths are renamed, and prose and bad lines are kept.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            None.
        """
        workspace = _OldWorkspace(tmp_path)
        workspace.migration().run()
        journal = (
            workspace.root
            / 'traders'
            / 'scalper'
            / 'journal'
            / '2026-10-20.jsonl'
        )
        lines = journal.read_text(encoding='utf-8').splitlines()
        event = json.loads(lines[0])
        assert event['kind'] == 'trader_started'
        assert event['trader'] == 'scalper'
        assert event['data']['trader_pnl'] == 12.5
        assert event['data']['tool_name'] == 'flatten_trader'
        assert event['data']['text'] == 'The desk is flat.'
        assert event['data']['path'] == (
            'workspace/traders/scalper/uploads/a.png'
        )
        assert lines[1] == 'not json but mentions desk'
        gateway_event = json.loads(
            (workspace.root / 'journal' / '2026-10-20.jsonl').read_text(
                encoding='utf-8'
            )
        )
        assert gateway_event == {
            'kind': 'error',
            'trader': None,
        }

    def test_cron_target_and_pairing_are_renamed(self, tmp_path: Path) -> None:
        """A cron job's "desk" target and a chat's desk become trader ones.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            None.
        """
        workspace = _OldWorkspace(tmp_path)
        workspace.migration().run()
        jobs = json.loads(
            (
                workspace.root / 'traders' / 'scalper' / 'cron' / 'jobs.json'
            ).read_text(encoding='utf-8')
        )
        assert jobs[0]['target'] == 'trader'
        assert jobs[0]['instructions'] == 'Check the desk.'
        pairing = json.loads(
            workspace.layout.telegram_pairing_file.read_text(encoding='utf-8')
        )
        assert pairing['paired'][0]['trader'] == 'general'

    def test_rules_tables_are_renamed(self, tmp_path: Path) -> None:
        """[desks.<name>] becomes [traders.<name>], and the prose is kept.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            None.
        """
        workspace = _OldWorkspace(tmp_path)
        workspace.migration().run()
        text = (
            workspace.layout.shared_directory / 'TradingRules.md'
        ).read_text(encoding='utf-8')
        assert '[traders.scalper]' in text
        assert '[desks.' not in text
        assert 'Each desk follows these.' in text

    def test_databases_are_renamed(self, tmp_path: Path) -> None:
        """The order book moves to trader_orders.db, and the columns become trader.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            None.
        """
        workspace = _OldWorkspace(tmp_path)
        workspace.migration().run()
        assert not (
            workspace.layout.shared_directory / 'desk_orders.db'
        ).exists()
        orders = sqlite3.connect(workspace.layout.trader_orders_file)
        assert orders.execute(
            'SELECT trader FROM trader_orders'
        ).fetchall() == [
            ('scalper',),
        ]
        orders.close()
        ledger = sqlite3.connect(workspace.layout.risk_ledger_file)
        assert ledger.execute('SELECT trader FROM ownership').fetchall() == [
            ('scalper',),
        ]
        ledger.execute('SELECT trader FROM approvals')
        ledger.execute('SELECT trader FROM day_owners')
        ledger.close()

    def test_checkpoint_and_terminal_settings_are_updated(
        self, tmp_path: Path
    ) -> None:
        """The checkpoint config points at the trader folder, and the terminal remembers the trader.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            None.
        """
        workspace = _OldWorkspace(tmp_path)
        workspace.migration().run()
        config = (
            workspace.root / '.checkpoints' / 'scalper.git' / 'config'
        ).read_text(encoding='utf-8')
        assert '/workspace/traders/scalper' in config
        settings = json.loads(
            workspace.terminal_file.read_text(encoding='utf-8')
        )
        assert settings == {
            'theme': 'dark',
            'trader': 'scalper',
        }

    def test_old_data_is_backed_up_first(self, tmp_path: Path) -> None:
        """The backup holds the old files as they were.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            None.
        """
        workspace = _OldWorkspace(tmp_path)
        workspace.migration().run()
        backup = workspace.root / '.backups' / 'desk-to-trader-20261101-090000'
        assert (backup / 'desks' / 'scalper' / 'Memory.md').exists()
        assert (backup / 'shared' / 'desk_orders.db').exists()
        assert '"desk"' in (backup / 'terminal.json').read_text(
            encoding='utf-8'
        )
        assert '[desks.scalper]' in (
            backup / 'shared' / 'TradingRules.md'
        ).read_text(encoding='utf-8')

    def test_second_run_changes_nothing(self, tmp_path: Path) -> None:
        """Once migrated, the workspace needs nothing more and no new backup is made.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            None.
        """
        workspace = _OldWorkspace(tmp_path)
        workspace.migration().run()
        assert not workspace.migration().needed()
        assert workspace.migration().run() == []
        backups = list((workspace.root / '.backups').iterdir())
        assert len(backups) == 1

    def test_new_workspace_needs_nothing(self, tmp_path: Path) -> None:
        """A workspace made after the rename is left alone.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            None.
        """
        layout = workspace_layout.WorkspaceLayout(tmp_path / 'workspace')
        layout.create_missing(['general'])
        migration = trader_migration.TraderMigration(
            layout,
            tmp_path / 'terminal.json',
            datetime.datetime(2026, 11, 1, tzinfo=datetime.UTC),
        )
        assert migration.run() == []
        assert not (tmp_path / 'workspace' / '.backups').exists()
