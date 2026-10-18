"""Tool calls in a row, folded into one summary line as Claude Code shows them.

Typical usage example:

  view = ToolRunView(run)
  view.show(run)
"""

from textual import widgets
from textual.content import Content

from trading_agent.terminal import chat_items
from trading_agent.terminal import tool_describer
from trading_agent.terminal.widgets import tool_call_view


class ToolRunView(widgets.Collapsible):
    """A run of tool calls."""

    def __init__(self, run: chat_items.ToolRun):
        """Creates the run's view.

        Args:
            run (chat_items.ToolRun): The tool calls.
        """
        super().__init__(
            title=self._title_content(run),
            collapsed=True,
            classes='tool-run',
        )
        self._run = run
        self._calls: list[tool_call_view.ToolCallView] = []

    def on_mount(self) -> None:
        """Adds the cards once the run is on screen."""
        self.show(self._run)

    def show(self, run: chat_items.ToolRun) -> None:
        """Updates the summary and the cards, adding cards for new calls.

        Args:
            run (chat_items.ToolRun): The tool calls, perhaps with more of them or more results.
        """
        self._run = run
        self.title = self._title_content(run)
        for index, step in enumerate(run.steps):
            if index < len(self._calls):
                self._calls[index].show(step)
                continue
            card = tool_call_view.ToolCallView(step)
            self._calls.append(card)
            self.query_one(widgets.Collapsible.Contents).mount(card)

    def expand_all(self, expanded: bool) -> None:
        """Opens or folds the run and every card in it.

        Args:
            expanded (bool): True to open, False to fold.
        """
        self.collapsed = not expanded
        for card in self._calls:
            card.collapsed = not expanded

    def _title_content(self, run: chat_items.ToolRun) -> Content:
        """The run's summary line.

        Args:
            run (chat_items.ToolRun): The tool calls.

        Returns:
            Content: Such as "Fetched 2 quotes, ran a command (1 failed)", with "…" while one is still running.
        """
        calls = []
        running = False
        for step in run.steps:
            calls.append(
                (
                    step.name,
                    step.is_error,
                )
            )
            if step.result_text is None and not step.ended_early:
                running = True
        summary = tool_describer.ToolDescriber().summary(calls)
        if running:
            summary += ' …'
        return Content(summary)
