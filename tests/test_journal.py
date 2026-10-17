"""Tests for the secret redactor and the trade journal."""

import datetime
import json
from pathlib import Path

from trading_agent.journal import secret_redactor
from trading_agent.journal import trade_journal
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.workspace import workspace_layout


class TestSecretRedactor:
    """Tests for masking secrets."""

    def test_known_value_is_masked_everywhere_in_nested_data(self) -> None:
        """A known secret is replaced in strings inside dictionaries and lists."""
        redactor = secret_redactor.SecretRedactor(['mongo-password-123'])

        redacted = redactor.redact(
            {
                'text': 'login with mongo-password-123 failed',
                'items': [
                    'mongo-password-123',
                    5,
                ],
            }
        )

        assert redacted == {
            'text': 'login with [redacted] failed',
            'items': [
                '[redacted]',
                5,
            ],
        }

    def test_token_shapes_are_masked_without_being_known(self) -> None:
        """Anthropic tokens, bearer tokens, token= and api-key values are masked by their shape."""
        redactor = secret_redactor.SecretRedactor([])

        text = redactor.redact(
            'key sk-ant-oat01-abcdefghijklmnop, header Bearer abcdefghijklmnopqrstuvwxyz, url /ws?token=xyz123&desk=main, api-key: s3cr3tvalue'
        )

        assert 'sk-ant-oat01' not in text
        assert 'abcdefghijklmnopqrstuvwxyz' not in text
        assert 'token=[redacted]&desk=main' in text
        assert 's3cr3tvalue' not in text

    def test_short_values_are_not_treated_as_secrets(self) -> None:
        """Values under eight characters are ignored, so ordinary words are never masked."""
        redactor = secret_redactor.SecretRedactor(['nse'])

        assert redactor.redact('nse equities') == 'nse equities'

    def test_tradingmachine_secrets_are_read_by_name(
        self, tmp_path: Path
    ) -> None:
        """From tradingmachine's .env, values named like passwords and keys are masked and others are not.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        environment_file = tmp_path / '.env'
        environment_file.write_text(
            '\n'.join(
                [
                    'TRADINGMACHINE_MONGODB_PASSWORD=very-secret-password',
                    'TRADINGMACHINE_UBI_BASE_URL=http://127.0.0.1:8080',
                ]
            ),
            encoding='utf-8',
        )

        class _Secrets:
            """Stands in for the agent's secrets."""

            gateway_access_token = 'gateway-token-abcdefgh'
            claude_code_oauth_token = ''
            openai_api_key = ''
            webhook_token = 'webhook-token-12345678'

        redactor = secret_redactor.SecretRedactor.from_files(
            _Secrets(), environment_file
        )

        assert redactor.redact('very-secret-password') == '[redacted]'
        assert redactor.redact('gateway-token-abcdefgh') == '[redacted]'
        assert (
            redactor.redact('http://127.0.0.1:8080') == 'http://127.0.0.1:8080'
        )


class TestTradeJournal:
    """Tests for writing the journal."""

    def _journal(self, tmp_path: Path) -> trade_journal.TradeJournal:
        """Builds a journal in a temporary workspace.

        Args:
            tmp_path (Path): A temporary folder from pytest.

        Returns:
            trade_journal.TradeJournal: The journal.
        """
        return trade_journal.TradeJournal(
            event_bus_module.EventBus(),
            workspace_layout.WorkspaceLayout(tmp_path / 'workspace'),
            secret_redactor.SecretRedactor(['super-secret-token-value']),
        )

    def _event(
        self,
        kind: event_module.EventKind,
        desk: str | None,
        payload: dict,
    ) -> event_module.Event:
        """Builds an event at 23:00 UTC on 2026-10-16, which is already 2026-10-17 in India.

        Args:
            kind (event_module.EventKind): The kind.
            desk (str | None): The desk.
            payload (dict): The payload.

        Returns:
            event_module.Event: The event.
        """
        return event_module.Event(
            kind=kind,
            desk=desk,
            payload=payload,
            created_at=datetime.datetime(
                2026, 10, 16, 23, 0, tzinfo=datetime.UTC
            ),
        )

    def test_events_go_to_the_desk_file_for_the_india_date(
        self, tmp_path: Path
    ) -> None:
        """An event is appended to its desk's file, named by the date in India, with secrets masked.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        journal = self._journal(tmp_path)

        journal.record(
            self._event(
                event_module.EventKind.TOOL_RESULT,
                'main',
                {
                    'text': 'answer with super-secret-token-value',
                },
            )
        )
        journal.record(
            self._event(event_module.EventKind.TURN_FINISHED, 'main', {})
        )

        path = (
            tmp_path
            / 'workspace'
            / 'desks'
            / 'main'
            / 'journal'
            / '2026-10-17.jsonl'
        )
        lines = path.read_text(encoding='utf-8').splitlines()
        first = json.loads(lines[0])
        assert len(lines) == 2
        assert first['kind'] == 'tool_result'
        assert first['payload']['text'] == 'answer with [redacted]'

    def test_text_pieces_are_left_out(self, tmp_path: Path) -> None:
        """Streamed text pieces are not written, because the final text event holds the reply.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        journal = self._journal(tmp_path)

        journal.record(
            self._event(
                event_module.EventKind.TEXT_DELTA,
                'main',
                {
                    'text': 'Hel',
                },
            )
        )

        assert not (
            tmp_path / 'workspace' / 'desks' / 'main' / 'journal'
        ).exists()

    def test_event_without_a_desk_goes_to_the_gateway_journal(
        self, tmp_path: Path
    ) -> None:
        """An event that belongs to no desk is written to the workspace's own journal folder.

        Args:
            tmp_path (Path): A temporary folder from pytest.
        """
        journal = self._journal(tmp_path)
        event = self._event(event_module.EventKind.ERROR, None, {})

        assert (
            journal.path_for(event)
            == tmp_path / 'workspace' / 'journal' / '2026-10-17.jsonl'
        )
