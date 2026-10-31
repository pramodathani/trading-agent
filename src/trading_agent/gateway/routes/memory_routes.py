"""Routes for what the traders remember: sessions, summaries, notes, the journal and session search.

  GET /api/traders/{trader}/sessions                the trader's sessions, newest first
  GET /api/traders/{trader}/sessions/{session_id}   one session's exchanges
  GET /api/traders/{trader}/summaries               the daily summaries
  GET /api/traders/{trader}/notes                   the daily notes files
  GET /api/traders/{trader}/search?keywords=...     search_sessions, as the trader sees it
  GET /api/traders/{trader}/journal?day=...         the trader's journal for a day
  GET /api/journal?day=...                      the gateway's own journal, for events without a trader

Session ids and days are checked against a strict pattern before they become file names, so a request cannot reach outside the trader's folder.

Typical usage example:

  application.include_router(MemoryRoutes(guard, parts, layout).router())
"""

import datetime
import re
import zoneinfo
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import fastapi

from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_parts
from trading_agent.gateway.routes import route_group
from trading_agent.journal import journal_reader
from trading_agent.memory import session_search
from trading_agent.workspace import workspace_layout

_INDIA = zoneinfo.ZoneInfo('Asia/Kolkata')
_SESSION_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}-\d{1,4}$')
_DAY_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_MOST_EVENTS = 2000


class MemoryRoutes(route_group.RouteGroup):
    """The memory routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        parts: Mapping[str, gateway_parts.TraderParts],
        layout: workspace_layout.WorkspaceLayout,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            parts (Mapping[str, gateway_parts.TraderParts]): Each trader's stores, keyed by trader name.
            layout (workspace_layout.WorkspaceLayout): Where the journals and notes are.
        """
        super().__init__(guard)
        self._parts = parts
        self._layout = layout

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the memory routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route(
            '/api/traders/{trader_name}/sessions',
            self.sessions,
            methods=['GET'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/sessions/{session_id}',
            self.session,
            methods=['GET'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/summaries',
            self.summaries,
            methods=['GET'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/notes', self.notes, methods=['GET']
        )
        router.add_api_route(
            '/api/traders/{trader_name}/search', self.search, methods=['GET']
        )
        router.add_api_route(
            '/api/traders/{trader_name}/journal',
            self.trader_journal,
            methods=['GET'],
        )
        router.add_api_route(
            '/api/journal', self.gateway_journal, methods=['GET']
        )

    def sessions(self, trader_name: str) -> dict[str, Any]:
        """The trader's sessions.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: The current session's id and every session with its number of exchanges.
        """
        store = self._find(self._parts, trader_name, 'trader').sessions
        state = store.load_state()
        sessions = []
        for session_id in store.session_ids():
            sessions.append(
                {
                    'session_id': session_id,
                    'exchanges': len(store.exchanges(session_id)),
                }
            )
        return {
            'current': state.session_id if state is not None else None,
            'sessions': sessions,
        }

    def session(self, trader_name: str, session_id: str) -> dict[str, Any]:
        """One session's exchanges.

        Args:
            trader_name (str): The trader.
            session_id (str): The session, such as 2026-10-19-1.

        Returns:
            dict[str, Any]: The exchanges, oldest first.

        Raises:
            fastapi.HTTPException: The id is not a session id (status 400).
        """
        store = self._find(self._parts, trader_name, 'trader').sessions
        if not _SESSION_PATTERN.match(session_id):
            raise fastapi.HTTPException(
                status_code=400, detail='Not a session id'
            )
        exchanges = []
        for exchange in store.exchanges(session_id):
            exchanges.append(exchange.to_json_dictionary())
        return {
            'session_id': session_id,
            'exchanges': exchanges,
        }

    def summaries(self, trader_name: str) -> dict[str, Any]:
        """The trader's daily summaries.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: The summaries, newest first.
        """
        store = self._find(self._parts, trader_name, 'trader').sessions
        summaries = []
        for summary in store.summaries():
            summaries.append(
                {
                    'date': summary.trading_date.isoformat(),
                    'text': summary.text,
                }
            )
        return {
            'summaries': summaries,
        }

    def notes(self, trader_name: str) -> dict[str, Any]:
        """The trader's notes files.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: Each notes file's name and text, newest first.
        """
        self._find(self._parts, trader_name, 'trader')
        folder = self._layout.notes_directory(trader_name)
        files = []
        if folder.is_dir():
            for path in sorted(folder.glob('*.md'), reverse=True):
                files.append(
                    {
                        'file': path.name,
                        'text': path.read_text(encoding='utf-8'),
                    }
                )
        return {
            'notes': files,
        }

    def search(
        self, trader_name: str, keywords: str, limit: int = 20
    ) -> dict[str, Any]:
        """Searches the trader's past, as search_sessions does.

        Args:
            trader_name (str): The trader.
            keywords (str): The keywords.
            limit (int): The most results.

        Returns:
            dict[str, Any]: The hits, best and newest first, and whether they hold every keyword.
        """
        self._find(self._parts, trader_name, 'trader')
        result = session_search.SessionSearch(
            self._layout.trader_directory(trader_name)
        ).search(keywords, max(1, min(limit, 100)))
        hits = []
        for hit in result.hits:
            hits.append(
                {
                    'day': hit.record.day,
                    'kind': hit.record.kind,
                    'snippet': hit.snippet,
                }
            )
        return {
            'matched_every_word': result.matched_every_word,
            'hits': hits,
        }

    def trader_journal(
        self,
        trader_name: str,
        day: str | None = None,
        kinds: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """A trader's journal for one day.

        Args:
            trader_name (str): The trader.
            day (str | None): The India date as YYYY-MM-DD, or None for today.
            kinds (str | None): Comma-separated event kinds to keep, or None for all.
            limit (int): The most events, the latest kept.

        Returns:
            dict[str, Any]: The day and its events, oldest first.
        """
        self._find(self._parts, trader_name, 'trader')
        folder = self._layout.trader_directory(trader_name) / 'journal'
        return self._journal(folder, day, kinds, limit)

    def gateway_journal(
        self,
        day: str | None = None,
        kinds: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """The gateway's own journal for one day, such as account status and kill-switch events.

        Args:
            day (str | None): The India date as YYYY-MM-DD, or None for today.
            kinds (str | None): Comma-separated event kinds to keep, or None for all.
            limit (int): The most events, the latest kept.

        Returns:
            dict[str, Any]: The day and its events, oldest first.
        """
        return self._journal(self._layout.root / 'journal', day, kinds, limit)

    def _journal(
        self,
        folder: Path,
        day: str | None,
        kinds: str | None,
        limit: int,
    ) -> dict[str, Any]:
        """Reads one journal file.

        Args:
            folder (Path): The journal folder.
            day (str | None): The India date, or None for today.
            kinds (str | None): Comma-separated kinds to keep, or None.
            limit (int): The most events.

        Returns:
            dict[str, Any]: The day and its events.

        Raises:
            fastapi.HTTPException: The day is not a date (status 400).
        """
        if day is None:
            day = datetime.datetime.now(_INDIA).date().isoformat()
        if not _DAY_PATTERN.match(day):
            raise fastapi.HTTPException(
                status_code=400, detail='day must be YYYY-MM-DD'
            )
        wanted = None
        if kinds:
            wanted = set()
            for kind in kinds.split(','):
                if kind.strip():
                    wanted.add(kind.strip())
        events = journal_reader.JournalReader(folder).events(day, wanted)
        limit = max(1, min(limit, _MOST_EVENTS))
        return {
            'day': day,
            'events': events[-limit:],
        }
