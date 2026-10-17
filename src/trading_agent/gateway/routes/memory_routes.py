"""Routes for what the desks remember: sessions, summaries, notes, the journal and session search.

  GET /api/desks/{desk}/sessions                the desk's sessions, newest first
  GET /api/desks/{desk}/sessions/{session_id}   one session's exchanges
  GET /api/desks/{desk}/summaries               the daily summaries
  GET /api/desks/{desk}/notes                   the daily notes files
  GET /api/desks/{desk}/search?keywords=...     search_sessions, as the desk sees it
  GET /api/desks/{desk}/journal?day=...         the desk's journal for a day
  GET /api/journal?day=...                      the gateway's own journal, for events without a desk

Session ids and days are checked against a strict pattern before they become file names, so a request cannot reach outside the desk's folder.

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
        parts: Mapping[str, gateway_parts.DeskParts],
        layout: workspace_layout.WorkspaceLayout,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            parts (Mapping[str, gateway_parts.DeskParts]): Each desk's stores, keyed by desk name.
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
            '/api/desks/{desk_name}/sessions', self.sessions, methods=['GET']
        )
        router.add_api_route(
            '/api/desks/{desk_name}/sessions/{session_id}',
            self.session,
            methods=['GET'],
        )
        router.add_api_route(
            '/api/desks/{desk_name}/summaries', self.summaries, methods=['GET']
        )
        router.add_api_route(
            '/api/desks/{desk_name}/notes', self.notes, methods=['GET']
        )
        router.add_api_route(
            '/api/desks/{desk_name}/search', self.search, methods=['GET']
        )
        router.add_api_route(
            '/api/desks/{desk_name}/journal', self.desk_journal, methods=['GET']
        )
        router.add_api_route(
            '/api/journal', self.gateway_journal, methods=['GET']
        )

    def sessions(self, desk_name: str) -> dict[str, Any]:
        """The desk's sessions.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The current session's id and every session with its number of exchanges.
        """
        store = self._find(self._parts, desk_name, 'desk').sessions
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

    def session(self, desk_name: str, session_id: str) -> dict[str, Any]:
        """One session's exchanges.

        Args:
            desk_name (str): The desk.
            session_id (str): The session, such as 2026-10-19-1.

        Returns:
            dict[str, Any]: The exchanges, oldest first.

        Raises:
            fastapi.HTTPException: The id is not a session id (status 400).
        """
        store = self._find(self._parts, desk_name, 'desk').sessions
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

    def summaries(self, desk_name: str) -> dict[str, Any]:
        """The desk's daily summaries.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The summaries, newest first.
        """
        store = self._find(self._parts, desk_name, 'desk').sessions
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

    def notes(self, desk_name: str) -> dict[str, Any]:
        """The desk's notes files.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: Each notes file's name and text, newest first.
        """
        self._find(self._parts, desk_name, 'desk')
        folder = self._layout.notes_directory(desk_name)
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
        self, desk_name: str, keywords: str, limit: int = 20
    ) -> dict[str, Any]:
        """Searches the desk's past, as search_sessions does.

        Args:
            desk_name (str): The desk.
            keywords (str): The keywords.
            limit (int): The most results.

        Returns:
            dict[str, Any]: The hits, best and newest first, and whether they hold every keyword.
        """
        self._find(self._parts, desk_name, 'desk')
        result = session_search.SessionSearch(
            self._layout.desk_directory(desk_name)
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

    def desk_journal(
        self,
        desk_name: str,
        day: str | None = None,
        kinds: str | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """A desk's journal for one day.

        Args:
            desk_name (str): The desk.
            day (str | None): The India date as YYYY-MM-DD, or None for today.
            kinds (str | None): Comma-separated event kinds to keep, or None for all.
            limit (int): The most events, the latest kept.

        Returns:
            dict[str, Any]: The day and its events, oldest first.
        """
        self._find(self._parts, desk_name, 'desk')
        folder = self._layout.desk_directory(desk_name) / 'journal'
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
