"""Tool calls in a row, folded into one summary line as Claude Code shows them.

Pictures the tools showed the model stay visible under the summary even while the run is folded, as on the web page.

Typical usage example:

  view = ToolRunView('general', run)
  view.show(run)
"""

from textual import containers
from textual import widgets
from textual.content import Content

from trading_agent.terminal import chat_items
from trading_agent.terminal import tool_describer
from trading_agent.terminal.widgets import picture_view
from trading_agent.terminal.widgets import tool_call_view


class ToolRunView(containers.Vertical):
    """A run of tool calls, with their pictures."""

    def __init__(self, trader_name: str, run: chat_items.ToolRun):
        """Creates the run's view.

        Args:
            trader_name (str): The trader, whose folder the pictures are in.
            run (chat_items.ToolRun): The tool calls.
        """
        super().__init__(classes='tool-run')
        self._trader_name = trader_name
        self._run = run
        self._calls: list[tool_call_view.ToolCallView] = []
        self._fold = widgets.Collapsible(
            title=self._title_content(run), collapsed=True
        )
        self._pictures = containers.Vertical(classes='tool-pictures')
        self._shown_pictures: set[str] = set()

    def compose(self):
        """Builds the view.

        Yields:
            Widget: The folded run and the pictures under it.
        """
        yield self._fold
        yield self._pictures

    def on_mount(self) -> None:
        """Adds the cards once the run is on screen."""
        self.show(self._run)

    def show(self, run: chat_items.ToolRun) -> None:
        """Updates the summary, the cards and the pictures, adding new ones.

        Args:
            run (chat_items.ToolRun): The tool calls, perhaps with more of them or more results.
        """
        self._run = run
        self._fold.title = self._title_content(run)
        for index, step in enumerate(run.steps):
            if index < len(self._calls):
                self._calls[index].show(step)
            else:
                card = tool_call_view.ToolCallView(step)
                self._calls.append(card)
                self._fold.query_one(widgets.Collapsible.Contents).mount(card)
            if (
                step.picture_path
                and step.picture_path not in self._shown_pictures
            ):
                self._shown_pictures.add(step.picture_path)
                self._pictures.mount(
                    picture_view.PictureView(
                        self._trader_name, picture_path=step.picture_path
                    )
                )

    def expand_all(self, expanded: bool) -> None:
        """Opens or folds the run and every card in it.

        Args:
            expanded (bool): True to open, False to fold.
        """
        self._fold.collapsed = not expanded
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
