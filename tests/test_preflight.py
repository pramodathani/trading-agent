"""Tests for the going-live checks of `trading-agent preflight`."""

import json
from pathlib import Path

from trading_agent.channels import pairing_store
from trading_agent.doctor import doctor_check
from trading_agent.doctor.checks import dry_run_order_check
from trading_agent.doctor.checks import journal_search
from trading_agent.doctor.checks import ownership_conflict_check
from trading_agent.doctor.checks import telegram_pairing_check
from trading_agent.doctor.checks import trader_loss_limits_check
from trading_agent.doctor.checks import trading_mode_check
from trading_agent.workspace import workspace_layout


def _journal(
    directory: Path, events: list[dict]
) -> journal_search.JournalSearch:
    """Writes one day of main's journal and builds a search over it.

    Args:
        directory (Path): A scratch workspace.
        events (list[dict]): The journal's events.

    Returns:
        journal_search.JournalSearch: The search.
    """
    layout = workspace_layout.WorkspaceLayout(directory)
    folder = layout.trader_directory('main') / 'journal'
    folder.mkdir(parents=True)
    lines = [json.dumps(event) for event in events]
    (folder / '2026-10-19.jsonl').write_text(
        '\n'.join(lines) + '\n', encoding='utf-8'
    )
    return journal_search.JournalSearch(layout, ['main'])


class TestGoingLiveChecks:
    """Tests for the checks that only matter before trading live."""

    def test_dry_run_order_fails_until_one_is_placed(
        self, tmp_path: Path
    ) -> None:
        """Without a placed order the check fails; a placed dry-run order makes it pass."""
        empty = _journal(tmp_path / 'empty', [])
        placed = _journal(
            tmp_path / 'placed',
            [
                {
                    'kind': 'order',
                    'trader': 'main',
                    'created_at': '2026-10-19T04:00:00+00:00',
                    'payload': {
                        'action': 'placed',
                        'dry_run': True,
                    },
                },
            ],
        )

        assert (
            dry_run_order_check.DryRunOrderCheck(empty).run().status
            == doctor_check.CheckStatus.FAILED
        )
        result = dry_run_order_check.DryRunOrderCheck(placed).run()
        assert result.status == doctor_check.CheckStatus.OK
        assert 'dry run' in result.message

    def test_flatten_alone_is_not_an_order(self, tmp_path: Path) -> None:
        """A flatten with nothing to close does not count as an order through UBI."""
        search = _journal(
            tmp_path,
            [
                {
                    'kind': 'order',
                    'trader': 'main',
                    'payload': {
                        'action': 'flattened',
                        'dry_run': True,
                    },
                },
            ],
        )

        assert (
            dry_run_order_check.DryRunOrderCheck(search).run().status
            == doctor_check.CheckStatus.FAILED
        )

    def test_ownership_refusal_is_found(self, tmp_path: Path) -> None:
        """A refusal saying the stock belongs to another trader passes the check."""
        search = _journal(
            tmp_path,
            [
                {
                    'kind': 'risk_decision',
                    'trader': 'main',
                    'payload': {
                        'approved': False,
                        'reasons': [
                            'IDEA belongs to the intraday trader; one trader trades an instrument at a time.',
                        ],
                    },
                },
            ],
        )

        assert (
            ownership_conflict_check.OwnershipConflictCheck(search).run().status
            == doctor_check.CheckStatus.OK
        )
        assert (
            ownership_conflict_check.OwnershipConflictCheck(
                _journal(tmp_path / 'other', [])
            )
            .run()
            .status
            == doctor_check.CheckStatus.WARNING
        )

    def test_no_trader_limits_is_reported_as_a_choice(
        self, tmp_path: Path
    ) -> None:
        """With no trader limits the check passes and names the account limits."""
        layout = workspace_layout.WorkspaceLayout(tmp_path)
        layout.create_missing(
            [
                'main',
            ]
        )

        result = trader_loss_limits_check.TraderLossLimitsCheck(
            layout.trading_rules_file, ['main']
        ).run()

        assert result.status == doctor_check.CheckStatus.OK
        assert 'a day' in result.message

    def test_mode_and_telegram_are_warnings(self, tmp_path: Path) -> None:
        """Dry run and an unpaired phone are warnings, not failures, and live mode is OK."""
        store = pairing_store.PairingStore(tmp_path / 'pairing.json')

        assert (
            trading_mode_check.TradingModeCheck('dry_run').run().status
            == doctor_check.CheckStatus.WARNING
        )
        assert (
            trading_mode_check.TradingModeCheck('live').run().status
            == doctor_check.CheckStatus.OK
        )
        assert (
            telegram_pairing_check.TelegramPairingCheck(False, store)
            .run()
            .status
            == doctor_check.CheckStatus.WARNING
        )
