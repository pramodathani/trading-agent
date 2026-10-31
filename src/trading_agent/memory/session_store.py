"""Keeps a trader's sessions on disk, so a restart does not make the trader forget the day.

A session is one stretch of conversation, normally one India trading day. The store keeps three things in the trader's sessions folder:

  sessions/
    state.json                 which session is current, and what each backend needs to resume it
    2026-10-19-1.jsonl         every finished exchange of that session, one JSON line each
    summaries/2026-10-19.md    the summary written when that day's session ended

Typical usage example:

  store = SessionStore(Path('workspace/traders/main/sessions'))
  state = store.load_state()
  store.append_exchange(state.session_id, exchange)
"""

import dataclasses
import datetime
import json
import logging
import os
import zoneinfo
from collections.abc import Callable
from pathlib import Path
from typing import Any, Self

_LOGGER = logging.getLogger(__name__)
_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_STATE_FILE_NAME = 'state.json'
_SUMMARIES_FOLDER_NAME = 'summaries'


@dataclasses.dataclass(frozen=True)
class Exchange:
    """One finished turn: what the trader was told and what it answered.

    Attributes:
        trigger_text: The trigger's text.
        answer: The final answer.
        backend_name: The backend that answered.
        finished_at: When the turn finished, as an ISO 8601 string in UTC.
    """

    trigger_text: str
    answer: str
    backend_name: str
    finished_at: str

    def to_json_dictionary(self) -> dict[str, Any]:
        """Converts the exchange to a dictionary that json.dumps can write.

        Returns:
            dict[str, Any]: The exchange's fields.
        """
        return dataclasses.asdict(self)

    @classmethod
    def from_json_dictionary(cls, data: dict[str, Any]) -> Self:
        """Reads an exchange written by to_json_dictionary.

        Args:
            data (dict[str, Any]): The dictionary.

        Returns:
            Exchange: The exchange.

        Raises:
            KeyError: A field is missing.
        """
        return cls(
            trigger_text=data['trigger_text'],
            answer=data['answer'],
            backend_name=data['backend_name'],
            finished_at=data['finished_at'],
        )


@dataclasses.dataclass(frozen=True)
class RouteState:
    """What one backend needs to pick up the current session after a restart.

    Attributes:
        exchanges_seen: How many of the session's exchanges the backend already knows about.
        runner_state: What the backend's turn runner saved, such as Claude's session id, or None when it keeps nothing.
    """

    exchanges_seen: int
    runner_state: dict[str, Any] | None


@dataclasses.dataclass(frozen=True)
class SessionState:
    """Which session is current.

    Attributes:
        session_id: The session's identifier, such as "2026-10-19-1".
        trading_date: The India date the session belongs to.
        routes: Each backend's state, keyed by the backend's name.
    """

    session_id: str
    trading_date: datetime.date
    routes: dict[str, RouteState]

    def to_json_dictionary(self) -> dict[str, Any]:
        """Converts the state to a dictionary that json.dumps can write.

        Returns:
            dict[str, Any]: The state, with the date as an ISO 8601 string.
        """
        routes = {}
        for name, route in self.routes.items():
            routes[name] = {
                'exchanges_seen': route.exchanges_seen,
                'runner_state': route.runner_state,
            }
        return {
            'session_id': self.session_id,
            'trading_date': self.trading_date.isoformat(),
            'routes': routes,
        }

    @classmethod
    def from_json_dictionary(cls, data: dict[str, Any]) -> Self:
        """Reads a state written by to_json_dictionary.

        Args:
            data (dict[str, Any]): The dictionary.

        Returns:
            SessionState: The state.

        Raises:
            KeyError: A field is missing.
            ValueError: The date is not an ISO 8601 date.
        """
        routes = {}
        for name, route in data.get('routes', {}).items():
            routes[name] = RouteState(
                exchanges_seen=int(route.get('exchanges_seen', 0)),
                runner_state=route.get('runner_state'),
            )
        return cls(
            session_id=data['session_id'],
            trading_date=datetime.date.fromisoformat(data['trading_date']),
            routes=routes,
        )


@dataclasses.dataclass(frozen=True)
class DailySummary:
    """The summary written when one day's session ended.

    Attributes:
        trading_date: The day it summarises.
        text: The summary.
    """

    trading_date: datetime.date
    text: str


class SessionStore:
    """One trader's sessions folder.

    Attributes:
        directory: The sessions folder.
    """

    def __init__(
        self,
        directory: Path,
        date_source: Callable[[], datetime.date] | None = None,
    ):
        """Describes the folder without touching the disk.

        Args:
            directory (Path): The trader's sessions folder.
            date_source (Callable[[], datetime.date] | None): Returns today's India date; None uses the clock. Tests replace it.
        """
        self.directory = directory
        self._date_source = date_source

    def today(self) -> datetime.date:
        """Today's date in India, which decides when a new session starts.

        Returns:
            datetime.date: The date.
        """
        if self._date_source is not None:
            return self._date_source()
        return datetime.datetime.now(_INDIA).date()

    def load_state(self) -> SessionState | None:
        """Reads which session is current.

        A damaged state file is logged and treated as missing, so the trader starts a new session rather than not starting.

        Returns:
            SessionState | None: The state, or None when there is none yet.
        """
        path = self.directory / _STATE_FILE_NAME
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            return SessionState.from_json_dictionary(data)
        except OSError, ValueError, KeyError, TypeError, AttributeError:
            _LOGGER.exception('Could not read the session state %s', path)
            return None

    def save_state(self, state: SessionState) -> None:
        """Writes which session is current.

        The file is written beside the old one and then renamed over it, so a crash mid-write leaves the old state intact.

        Args:
            state (SessionState): The state.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / _STATE_FILE_NAME
        temporary_path = path.with_suffix('.json.tmp')
        temporary_path.write_text(
            json.dumps(state.to_json_dictionary(), indent=2),
            encoding='utf-8',
        )
        os.replace(temporary_path, path)

    def new_session_id(self, trading_date: datetime.date) -> str:
        """Picks the next free session identifier for a day and creates its empty log.

        Args:
            trading_date (datetime.date): The session's India date.

        Returns:
            str: An identifier such as "2026-10-19-2".
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        number = 1
        while self._log_path(f'{trading_date.isoformat()}-{number}').exists():
            number += 1
        session_id = f'{trading_date.isoformat()}-{number}'
        self._log_path(session_id).touch()
        return session_id

    def append_exchange(self, session_id: str, exchange: Exchange) -> None:
        """Adds one finished exchange to the end of a session's log.

        Args:
            session_id (str): The session.
            exchange (Exchange): The exchange.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        line = json.dumps(exchange.to_json_dictionary(), ensure_ascii=False)
        with self._log_path(session_id).open('a', encoding='utf-8') as log:
            log.write(line + '\n')

    def exchanges(self, session_id: str) -> list[Exchange]:
        """Reads a session's exchanges, oldest first.

        A damaged line, such as one cut short by a crash, is skipped.

        Args:
            session_id (str): The session.

        Returns:
            list[Exchange]: The exchanges, or an empty list for an unknown session.
        """
        path = self._log_path(session_id)
        if not path.is_file():
            return []
        exchanges = []
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            try:
                exchanges.append(
                    Exchange.from_json_dictionary(json.loads(line))
                )
            except ValueError, KeyError, TypeError:
                _LOGGER.warning('Skipped a damaged line in %s', path)
        return exchanges

    def session_ids(self) -> list[str]:
        """Every session that has a log, newest first.

        Returns:
            list[str]: The session identifiers.
        """
        if not self.directory.is_dir():
            return []
        ids = []
        for path in self.directory.glob('*.jsonl'):
            ids.append(path.stem)
        ids.sort(key=self._session_sort_key, reverse=True)
        return ids

    def summaries(self) -> list[DailySummary]:
        """Every daily summary, newest first.

        Returns:
            list[DailySummary]: The summaries.
        """
        folder = self.directory / _SUMMARIES_FOLDER_NAME
        if not folder.is_dir():
            return []
        summaries = []
        for path in folder.glob('*.md'):
            try:
                summary_date = datetime.date.fromisoformat(path.stem)
            except ValueError:
                continue
            summaries.append(
                DailySummary(
                    trading_date=summary_date,
                    text=path.read_text(encoding='utf-8').strip(),
                )
            )
        summaries.sort(key=lambda summary: summary.trading_date, reverse=True)
        return summaries

    def _session_sort_key(self, session_id: str) -> tuple[str, int]:
        """Orders session identifiers by date, then by number.

        Args:
            session_id (str): Such as "2026-10-19-2".

        Returns:
            tuple[str, int]: A tuple (date, number), where date is the identifier's date part and number its count within the day.
        """
        day, _, number = session_id.rpartition('-')
        if number.isdigit():
            return day, int(number)
        return session_id, 0

    def write_summary(self, trading_date: datetime.date, text: str) -> Path:
        """Saves the summary of a day's session.

        Args:
            trading_date (datetime.date): The day it summarises.
            text (str): The summary.

        Returns:
            Path: The summary's file.
        """
        folder = self.directory / _SUMMARIES_FOLDER_NAME
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f'{trading_date.isoformat()}.md'
        path.write_text(text.strip() + '\n', encoding='utf-8')
        return path

    def latest_summary(self) -> DailySummary | None:
        """Reads the most recent daily summary.

        Returns:
            DailySummary | None: The newest summary, or None when no day has been summarised yet.
        """
        folder = self.directory / _SUMMARIES_FOLDER_NAME
        if not folder.is_dir():
            return None
        newest_path = None
        newest_date = None
        for path in folder.glob('*.md'):
            try:
                summary_date = datetime.date.fromisoformat(path.stem)
            except ValueError:
                continue
            if newest_date is None or summary_date > newest_date:
                newest_date = summary_date
                newest_path = path
        if newest_path is None:
            return None
        return DailySummary(
            trading_date=newest_date,
            text=newest_path.read_text(encoding='utf-8').strip(),
        )

    def _log_path(self, session_id: str) -> Path:
        """The log file of one session.

        Args:
            session_id (str): The session.

        Returns:
            Path: The file.
        """
        return self.directory / f'{session_id}.jsonl'
