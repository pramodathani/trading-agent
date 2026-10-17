"""The search_knowledge tool: searches the user's documents in workspace/shared/knowledge/.

Typical usage example:

  tool = SearchKnowledgeTool(knowledge_base)
"""

import asyncio

import pydantic

from trading_agent.extensions import untrusted_text
from trading_agent.knowledge import knowledge_base as knowledge_base_module
from trading_agent.tools import tool


class SearchKnowledgeArguments(pydantic.BaseModel):
    """The arguments of search_knowledge.

    Attributes:
        query: A few words to look for.
        limit: The most passages to return.
    """

    model_config = pydantic.ConfigDict(extra='forbid')

    query: str = pydantic.Field(min_length=1)
    limit: int = pydantic.Field(default=5, gt=0, le=20)


class SearchKnowledgeTool(tool.Tool):
    """Returns the passages of the knowledge base that best match a query."""

    name = 'search_knowledge'
    description = "Searches the user's knowledge base: documents they put in workspace/shared/knowledge/, such as strategy write-ups, broker rules or exchange circulars. Give a few words; words match by their stem, so 'gapped' finds 'gap'. Results are the best passages with their file and heading. Read a whole file with read_file when a passage is not enough."
    arguments_model = SearchKnowledgeArguments

    def __init__(self, knowledge_base: knowledge_base_module.KnowledgeBase):
        """Creates the tool.

        Args:
            knowledge_base (knowledge_base_module.KnowledgeBase): The index.
        """
        self._knowledge_base = knowledge_base

    async def run(self, arguments: SearchKnowledgeArguments) -> tool.ToolResult:
        """Brings the index up to date, then searches it, in a worker thread.

        Args:
            arguments (SearchKnowledgeArguments): The query and the limit.

        Returns:
            tool.ToolResult: The passages, labelled as outside data, or a note that nothing matched.
        """
        counts = await asyncio.to_thread(self._knowledge_base.refresh)
        if counts.passages == 0:
            return tool.ToolResult.success(
                'The knowledge base is empty: the user has not put any .md, .txt or .csv files in workspace/shared/knowledge/ yet.'
            )
        hits = await asyncio.to_thread(
            self._knowledge_base.search,
            arguments.query,
            arguments.limit,
        )
        if not hits:
            return tool.ToolResult.success(
                f'Nothing in the knowledge base matches {arguments.query!r}.'
            )
        lines = []
        for hit in hits:
            lines.append(f'[{hit.path} · {hit.heading}]')
            lines.append(hit.snippet)
            lines.append('')
        return tool.ToolResult.success(
            untrusted_text.UntrustedText().wrap(
                'the knowledge base',
                '\n'.join(lines).strip(),
            )
        )
