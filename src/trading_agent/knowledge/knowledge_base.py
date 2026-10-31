"""A searchable index of the user's documents in workspace/shared/knowledge/.

Put Markdown, text or CSV files in the folder, such as strategy write-ups, broker rules or exchange circulars, and every trader can search them with search_knowledge. Each file is cut into passages of about 1,500 characters, kept under the nearest Markdown heading, and indexed with SQLite's FTS5 full-text search. Words are matched by their stem, so "gapped" finds "gap", and results are ranked by BM25, the usual relevance score of search engines.

The index lives in workspace/shared/knowledge.db. Before each search, files that were added, changed or removed since the last search are indexed again, so there is no separate import step.

Typical usage example:

  knowledge = KnowledgeBase(Path('workspace/shared/knowledge'), Path('workspace/shared/knowledge.db'))
  knowledge.refresh()
  hits = knowledge.search('opening range breakout', 5)
"""

import contextlib
import dataclasses
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

INDEXED_SUFFIXES = (
    '.md',
    '.markdown',
    '.txt',
    '.csv',
)
_PASSAGE_CHARACTERS = 1500
_WORD_PATTERN = re.compile(r'\w+')
_HEADING_PATTERN = re.compile(r'^#{1,6}\s+(.*)$')


@dataclasses.dataclass(frozen=True)
class KnowledgeHit:
    """One passage that matched.

    Attributes:
        path: The file, relative to the knowledge folder.
        heading: The Markdown heading the passage sits under, or the file name.
        snippet: The matching part, with matched words in [brackets].
    """

    path: str
    heading: str
    snippet: str


@dataclasses.dataclass(frozen=True)
class RefreshCounts:
    """What one refresh did.

    Attributes:
        indexed: Files indexed because they were new or changed.
        removed: Files dropped because they were deleted.
        passages: Passages in the index afterwards.
    """

    indexed: int
    removed: int
    passages: int


class KnowledgeBase:
    """The index over one knowledge folder."""

    def __init__(self, knowledge_directory: Path, index_file: Path):
        """Describes the knowledge base without touching the disk.

        Args:
            knowledge_directory (Path): The folder of documents.
            index_file (Path): The SQLite file holding the index.
        """
        self._knowledge_directory = knowledge_directory
        self._index_file = index_file

    def refresh(self) -> RefreshCounts:
        """Indexes new and changed files and forgets deleted ones.

        Returns:
            RefreshCounts: What changed.
        """
        current = {}
        for path in self._documents():
            status = path.stat()
            relative = str(path.relative_to(self._knowledge_directory))
            current[relative] = (status.st_mtime, status.st_size)
        with self._connection() as connection:
            known = {}
            for row in connection.execute(
                'select path, modified, size from files'
            ):
                known[row[0]] = (row[1], row[2])
            indexed = 0
            for relative, signature in current.items():
                if known.get(relative) == signature:
                    continue
                self._index_file_passages(connection, relative, signature)
                indexed += 1
            removed = 0
            for relative in known:
                if relative not in current:
                    connection.execute(
                        'delete from passages where path = ?', (relative,)
                    )
                    connection.execute(
                        'delete from files where path = ?', (relative,)
                    )
                    removed += 1
            passages = connection.execute(
                'select count(*) from passages'
            ).fetchone()[0]
        return RefreshCounts(
            indexed=indexed, removed=removed, passages=passages
        )

    def search(self, query: str, limit: int) -> list[KnowledgeHit]:
        """Finds the passages that best match the query.

        Passages holding every word come first; when there are none, passages holding any of the words are returned.

        Args:
            query (str): Words to look for.
            limit (int): The most passages to return.

        Returns:
            list[KnowledgeHit]: The best passages, most relevant first.
        """
        words = _WORD_PATTERN.findall(query.lower())
        if not words:
            return []
        quoted = []
        for word in words:
            quoted.append(f'"{word}"')
        with self._connection() as connection:
            hits = self._match(connection, ' AND '.join(quoted), limit)
            if not hits:
                hits = self._match(connection, ' OR '.join(quoted), limit)
        return hits

    def _match(
        self,
        connection: sqlite3.Connection,
        expression: str,
        limit: int,
    ) -> list[KnowledgeHit]:
        """Runs one FTS5 query.

        Args:
            connection (sqlite3.Connection): The open index.
            expression (str): The FTS5 match expression, made only of quoted words.
            limit (int): The most rows to return.

        Returns:
            list[KnowledgeHit]: The matching passages, best first.
        """
        rows = connection.execute(
            "select path, heading, snippet(passages, 2, '[', ']', '…', 40) from passages where passages match ? order by bm25(passages) limit ?",
            (expression, limit),
        ).fetchall()
        hits = []
        for row in rows:
            hits.append(
                KnowledgeHit(path=row[0], heading=row[1], snippet=row[2])
            )
        return hits

    def _index_file_passages(
        self,
        connection: sqlite3.Connection,
        relative: str,
        signature: tuple[float, int],
    ) -> None:
        """Replaces one file's passages in the index.

        Args:
            connection (sqlite3.Connection): The open index.
            relative (str): The file, relative to the knowledge folder.
            signature (tuple[float, int]): A tuple (modified, size), where modified is the file's modification time and size its length in bytes.
        """
        path = self._knowledge_directory / relative
        text = path.read_text(encoding='utf-8', errors='replace')
        connection.execute('delete from passages where path = ?', (relative,))
        for heading, body in self._passages(text, path.name):
            connection.execute(
                'insert into passages (path, heading, body) values (?, ?, ?)',
                (relative, heading, body),
            )
        connection.execute(
            'insert or replace into files (path, modified, size) values (?, ?, ?)',
            (relative, signature[0], signature[1]),
        )

    def _passages(self, text: str, file_name: str) -> Iterator[tuple[str, str]]:
        """Cuts a document into passages under their headings.

        Args:
            text (str): The document.
            file_name (str): Used as the heading before the first Markdown heading.

        Yields:
            tuple[str, str]: A tuple (heading, body), where heading is the nearest heading and body at most about 1,500 characters of paragraphs.
        """
        heading = file_name
        pending = []
        size = 0
        for paragraph in re.split(r'\n\s*\n', text):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            match = _HEADING_PATTERN.match(paragraph.splitlines()[0])
            if match is not None:
                if pending:
                    yield heading, '\n\n'.join(pending)
                    pending = []
                    size = 0
                heading = match.group(1).strip()
            if pending and size + len(paragraph) > _PASSAGE_CHARACTERS:
                yield heading, '\n\n'.join(pending)
                pending = []
                size = 0
            pending.append(paragraph)
            size += len(paragraph)
        if pending:
            yield heading, '\n\n'.join(pending)

    def _documents(self) -> list[Path]:
        """The indexable files in the knowledge folder, at any depth.

        Returns:
            list[Path]: The files, sorted.
        """
        if not self._knowledge_directory.is_dir():
            return []
        documents = []
        for path in sorted(self._knowledge_directory.rglob('*')):
            if path.is_file() and path.suffix.lower() in INDEXED_SUFFIXES:
                documents.append(path)
        return documents

    @contextlib.contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Opens the index, creating its tables the first time, and commits on success.

        Yields:
            sqlite3.Connection: The open connection.
        """
        self._index_file.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._index_file, timeout=30)
        try:
            connection.execute(
                'create table if not exists files (path text primary key, modified real, size integer)'
            )
            connection.execute(
                "create virtual table if not exists passages using fts5(path unindexed, heading, body, tokenize = 'porter unicode61')"
            )
            yield connection
            connection.commit()
        finally:
            connection.close()
