"""The search_sessions tool: finds what the desk said and did before.

Typical usage example:

  tool = SearchSessionsTool(SessionSearch(desk_directory))
"""

import asyncio

import pydantic

from trading_agent.memory import session_search as session_search_module
from trading_agent.tools import tool


class SearchSessionsArguments(pydantic.BaseModel):
    """The arguments of search_sessions.

    Attributes:
        keywords: A few keywords separated by spaces, such as "NIFTY gap down".
        limit: The most results to return.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    keywords: str = pydantic.Field(min_length=1)
    limit: int = pydantic.Field(default=10, gt=0, le=30)


class SearchSessionsTool(tool.Tool):
    """Searches the desk's past sessions, summaries, notes and journal."""

    name = 'search_sessions'
    description = 'Searches your past: earlier exchanges with the user and triggers, the daily summaries of your sessions, your notes, and the journal of your orders, risk decisions and tool calls. Give a few keywords, not a question, such as "NIFTY gap down" or "INFY bracket". A result contains every keyword, ignoring case; when none does, results with some of them are shown. Results are best and newest first, each with its date.'
    arguments_model = SearchSessionsArguments

    def __init__(self, search: session_search_module.SessionSearch):
        """Creates the tool.

        Args:
            search (session_search_module.SessionSearch): The desk's search.
        """
        self._search = search

    async def run(self, arguments: SearchSessionsArguments) -> tool.ToolResult:
        """Runs the search in a worker thread, because it reads many files.

        Args:
            arguments (SearchSessionsArguments): The keywords and the limit.

        Returns:
            tool.ToolResult: The hits, one block each, or a note that nothing matched.
        """
        result = await asyncio.to_thread(
            self._search.search,
            arguments.keywords,
            arguments.limit,
        )
        if not result.words:
            return tool.ToolResult.error(
                'Give at least one keyword made of letters or digits.'
            )
        if not result.hits:
            return tool.ToolResult.success(
                f'Nothing in your past matches any of: {", ".join(result.words)}.'
            )
        if result.matched_every_word:
            heading = f'{len(result.hits)} result(s) containing every keyword:'
        else:
            heading = f'Nothing contains every keyword, so these {len(result.hits)} result(s) contain some of them:'
        lines = [
            heading,
        ]
        for hit in result.hits:
            lines.append('')
            lines.append(f'[{hit.record.day} · {hit.record.kind}]')
            lines.append(hit.snippet)
        return tool.ToolResult.success('\n'.join(lines))
