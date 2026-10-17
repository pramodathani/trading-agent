# knowledge_base.py

The RAG knowledge base (block 29): SQLite FTS5 over `workspace/shared/knowledge/`, searched with `search_knowledge`.

## Decisions

- **FTS5, not embeddings.** Keyword search with the Porter stemmer (so "gapped" matches "gap") and BM25 ranking needs no model, no GPU time and no extra service, and the SQLite bundled with Python has it (3.46.1, checked). Meaning-based search with Ollama embeddings is in the backlog.
- **Passages under headings.** Files are cut at blank lines into passages of about 1,500 characters, never across a Markdown heading, and each passage keeps its heading, so a hit says where in the document it is.
- **Incremental, automatic refresh.** Each search first compares every file's modification time and size with the index and re-indexes only what changed, and drops deleted files. Users just drop files in the folder; there is no import command.
- **AND, then OR.** Passages containing every query word come first; if there are none, passages with any of them. Query words are reduced to letters and digits and quoted, so a query can never be read as FTS5 syntax.
- **Formats.** `.md`, `.markdown`, `.txt` and `.csv`. PDF extraction is in the backlog.
- The index is `workspace/shared/knowledge.db`, ignored by git; it can be deleted at any time and is rebuilt on the next search.
- One connection per call, so the tool can run it in a worker thread; SQLite's own locking (30-second timeout) handles two desks searching at once.
