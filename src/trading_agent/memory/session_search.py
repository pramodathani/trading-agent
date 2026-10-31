"""Keyword search over everything a trader has said and done before.

It looks through four kinds of record in the trader folder, newest days first:

- exchanges: each trigger and the trader's answer, paired from the journal's trigger_received and text events;
- journal: the trader's actions, such as orders, risk decisions and tool calls, from journal/*.jsonl;
- summaries: each paragraph of the daily summaries, from sessions/summaries/*.md;
- notes: each note, from notes/*.md.

The journal is the complete record, going back before sessions were kept, so exchanges come from it rather than from the session logs, which exist to resume a session. The trader's own search_sessions calls are left out, so a search never finds itself.

A record matches when it contains every keyword, ignoring case. When nothing matches every keyword, records that match some of them are returned instead, best first.

Typical usage example:

  search = SessionSearch(Path('workspace/traders/main'))
  hits = search.search('NIFTY gap down', limit=10)
"""

import dataclasses
import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
_ACTION_KINDS = (
    'tool_call',
    'order',
    'risk_decision',
    'kill_switch',
    'backend_switch',
    'error',
)
_TRIGGER_KIND = 'trigger_received'
_ANSWER_KIND = 'text'
_SEARCH_TOOL_NAME = 'search_sessions'
_SNIPPET_CHARACTERS = 500
_WORD_PATTERN = re.compile(r'[\w.&-]+')


@dataclasses.dataclass(frozen=True)
class SearchRecord:
    """One searchable record.

    Attributes:
        day: The India date it belongs to, as YYYY-MM-DD.
        kind: "exchange", "summary", "note" or "journal".
        text: The record's text.
    """

    day: str
    kind: str
    text: str


@dataclasses.dataclass(frozen=True)
class SearchHit:
    """One record that matched.

    Attributes:
        record: The record.
        matched_words: How many of the keywords it contains.
        snippet: The part of its text around the first keyword.
    """

    record: SearchRecord
    matched_words: int
    snippet: str


@dataclasses.dataclass(frozen=True)
class SearchResult:
    """The outcome of one search.

    Attributes:
        hits: The matching records, best and newest first.
        matched_every_word: Whether the hits contain every keyword, or only some.
        words: The keywords searched for.
    """

    hits: list[SearchHit]
    matched_every_word: bool
    words: list[str]


class SessionSearch:
    """Searches one trader's records."""

    def __init__(self, trader_directory: Path):
        """Creates the search.

        Args:
            trader_directory (Path): The trader folder.
        """
        self._trader_directory = trader_directory

    def search(self, query: str, limit: int) -> SearchResult:
        """Finds the records that best match the keywords.

        Args:
            query (str): Keywords separated by spaces.
            limit (int): The most hits to return.

        Returns:
            SearchResult: The hits.
        """
        words = self._words(query)
        if not words:
            return SearchResult(hits=[], matched_every_word=False, words=[])
        full_hits = []
        partial_hits = []
        for record in self._records(words):
            lowered = record.text.lower()
            matched = 0
            for word in words:
                if word in lowered:
                    matched += 1
            if matched == 0:
                continue
            hit = SearchHit(
                record=record,
                matched_words=matched,
                snippet=self._snippet(record.text, lowered, words),
            )
            if matched == len(words):
                full_hits.append(hit)
            else:
                partial_hits.append(hit)
        if full_hits:
            return SearchResult(
                hits=self._best(full_hits, limit),
                matched_every_word=True,
                words=words,
            )
        return SearchResult(
            hits=self._best(partial_hits, limit),
            matched_every_word=False,
            words=words,
        )

    def _words(self, query: str) -> list[str]:
        """Splits a query into distinct lower-case keywords.

        Args:
            query (str): The query.

        Returns:
            list[str]: The keywords, in the order given, without repeats.
        """
        words = []
        for word in _WORD_PATTERN.findall(query.lower()):
            word = word.strip('.-')
            if word and word not in words:
                words.append(word)
        return words

    def _best(self, hits: list[SearchHit], limit: int) -> list[SearchHit]:
        """Orders hits by how many keywords they match, then newest first.

        Args:
            hits (list[SearchHit]): The hits.
            limit (int): How many to keep.

        Returns:
            list[SearchHit]: The best hits.
        """
        ordered = sorted(
            hits,
            key=lambda hit: (hit.matched_words, hit.record.day),
            reverse=True,
        )
        return ordered[:limit]

    def _snippet(self, text: str, lowered: str, words: list[str]) -> str:
        """Cuts the part of a record around its first keyword.

        Args:
            text (str): The record's text.
            lowered (str): The same text in lower case.
            words (list[str]): The keywords.

        Returns:
            str: At most 500 characters, with "…" where text was cut.
        """
        flattened = ' '.join(text.split())
        if len(flattened) <= _SNIPPET_CHARACTERS:
            return flattened
        flattened_lowered = ' '.join(lowered.split())
        first = len(flattened_lowered)
        for word in words:
            position = flattened_lowered.find(word)
            if 0 <= position < first:
                first = position
        start = max(0, first - _SNIPPET_CHARACTERS // 4)
        end = start + _SNIPPET_CHARACTERS
        snippet = flattened[start:end]
        if start > 0:
            snippet = '…' + snippet
        if end < len(flattened):
            snippet = snippet + '…'
        return snippet

    def _records(self, words: list[str]) -> Iterator[SearchRecord]:
        """Yields every record that might contain a keyword.

        Lines that contain none of the keywords are skipped before they are parsed, which keeps a search over months of journal fast.

        Args:
            words (list[str]): The keywords.

        Yields:
            SearchRecord: The next record.
        """
        yield from self._journal_records(
            self._trader_directory / 'journal',
            words,
        )
        yield from self._summary_records(
            self._trader_directory / 'sessions' / 'summaries'
        )
        yield from self._note_records(self._trader_directory / 'notes')

    def _summary_records(self, directory: Path) -> Iterator[SearchRecord]:
        """Yields each paragraph of each daily summary.

        Args:
            directory (Path): The summaries folder.

        Yields:
            SearchRecord: One paragraph.
        """
        if not directory.is_dir():
            return
        for path in sorted(directory.glob('*.md'), reverse=True):
            text = self._read(path)
            for paragraph in text.split('\n\n'):
                if paragraph.strip():
                    yield SearchRecord(
                        day=path.stem,
                        kind='summary',
                        text=paragraph.strip(),
                    )

    def _note_records(self, directory: Path) -> Iterator[SearchRecord]:
        """Yields each note of each notes file.

        Args:
            directory (Path): The notes folder.

        Yields:
            SearchRecord: One note.
        """
        if not directory.is_dir():
            return
        for path in sorted(directory.glob('*.md'), reverse=True):
            for line in self._read(path).splitlines():
                if line.startswith('- '):
                    yield SearchRecord(
                        day=path.stem[:10],
                        kind='note',
                        text=line[2:],
                    )

    def _journal_records(
        self,
        directory: Path,
        words: list[str],
    ) -> Iterator[SearchRecord]:
        """Yields the exchanges and actions recorded in the trader's journal.

        Each journal line starts with its kind, so lines of other kinds, such as long tool results, are skipped without being parsed. A trigger is kept until its answer arrives, so the pair can be searched as one exchange.

        Args:
            directory (Path): The trader's journal folder.
            words (list[str]): The keywords, used to skip action lines early.

        Yields:
            SearchRecord: One exchange or action.
        """
        if not directory.is_dir():
            return
        for path in sorted(directory.glob('*.jsonl'), reverse=True):
            day = path.stem[:10]
            trigger_texts = {}
            for line in self._read(path).splitlines():
                kind = self._line_kind(line)
                if kind == _TRIGGER_KIND:
                    payload = self._payload(line)
                    trigger_texts[payload.get('trigger_id')] = str(
                        payload.get('text', '')
                    )
                elif kind == _ANSWER_KIND:
                    payload = self._payload(line)
                    trigger_text = trigger_texts.pop(
                        payload.get('trigger_id'), ''
                    )
                    yield SearchRecord(
                        day=day,
                        kind='exchange',
                        text=f'Trigger: {trigger_text}\nAnswer: {payload.get("text", "")}',
                    )
                elif kind in _ACTION_KINDS and self._has_a_word(line, words):
                    record = self._action_record(day, line)
                    if record is not None:
                        yield record

    def _line_kind(self, line: str) -> str | None:
        """Reads a journal line's kind from its start, without parsing the line.

        Args:
            line (str): One journal line, which starts with {"kind": "<kind>".

        Returns:
            str | None: The kind, or None when the line does not start that way.
        """
        prefix = '{"kind": "'
        if not line.startswith(prefix):
            return None
        end = line.find('"', len(prefix))
        if end == -1:
            return None
        return line[len(prefix) : end]

    def _payload(self, line: str) -> dict:
        """Parses a journal line and returns its payload.

        Args:
            line (str): One journal line.

        Returns:
            dict: The payload, or an empty dictionary when the line is damaged.
        """
        try:
            payload = json.loads(line).get('payload', {})
        except ValueError, AttributeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    def _action_record(self, day: str, line: str) -> SearchRecord | None:
        """Turns one action line into a record, leaving out the trader's own searches.

        Args:
            day (str): The journal file's date.
            line (str): The journal line.

        Returns:
            SearchRecord | None: The record, or None for a damaged line or a search_sessions call.
        """
        try:
            data = json.loads(line)
        except ValueError:
            return None
        payload = data.get('payload', {})
        if payload.get('name') == _SEARCH_TOOL_NAME:
            return None
        time_text = str(data.get('created_at', ''))[11:16]
        return SearchRecord(
            day=day,
            kind='journal',
            text=f'{time_text} UTC {data.get("kind")}: {json.dumps(payload, ensure_ascii=False)}',
        )

    def _has_a_word(self, line: str, words: list[str]) -> bool:
        """Says whether a line contains at least one keyword, ignoring case.

        Args:
            line (str): The line.
            words (list[str]): The keywords.

        Returns:
            bool: True when one of them appears.
        """
        lowered = line.lower()
        for word in words:
            if word in lowered:
                return True
        return False

    def _read(self, path: Path) -> str:
        """Reads a file, treating one that cannot be read as empty.

        Args:
            path (Path): The file.

        Returns:
            str: Its text, or an empty string.
        """
        try:
            return path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            _LOGGER.warning('Could not read %s for a search', path)
            return ''
