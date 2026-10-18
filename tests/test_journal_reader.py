"""Tests for reading one day of a journal folder."""

import datetime
import zoneinfo
from pathlib import Path

from trading_agent.journal import journal_reader

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')


class TestJournalReader:
    """Tests for JournalReader."""

    def test_today_is_the_india_date(self, tmp_path: Path) -> None:
        """Just after midnight in India, today is already the India date, although it is still the day before in UTC."""
        clock = datetime.datetime(2026, 10, 18, 19, 0, tzinfo=datetime.UTC)
        reader = journal_reader.JournalReader(tmp_path, lambda: clock)

        assert reader.today() == '2026-10-19'

    def test_events_keep_the_wanted_kinds_and_skip_bad_lines(
        self, tmp_path: Path
    ) -> None:
        """Only the asked-for kinds are returned, oldest first, and a line that is not JSON is skipped."""
        (tmp_path / '2026-10-19.jsonl').write_text(
            '\n'.join(
                [
                    '{"kind": "order", "payload": {"n": 1}}',
                    'not json',
                    '{"kind": "text", "payload": {}}',
                    '{"kind": "fill", "payload": {"n": 2}}',
                ]
            ),
            encoding='utf-8',
        )
        reader = journal_reader.JournalReader(tmp_path)

        events = reader.events(
            '2026-10-19',
            (
                'order',
                'fill',
            ),
        )

        assert [event['payload']['n'] for event in events] == [
            1,
            2,
        ]
        assert len(reader.events('2026-10-19')) == 3
        assert reader.events('2026-10-20') == []
