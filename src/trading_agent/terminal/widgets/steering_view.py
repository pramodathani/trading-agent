"""A message the user sent while a turn was running, shown inside that turn.

Typical usage example:

  view = SteeringView(step)
  view.show(step)
"""

from textual import widgets
from textual.content import Content

from trading_agent.terminal import chat_items
from trading_agent.terminal import formatter


class SteeringView(widgets.Static):
    """The steering message and whether it reached the running turn."""

    def __init__(self, step: chat_items.SteeringStep):
        """Creates the view.

        Args:
            step (chat_items.SteeringStep): The steering step.
        """
        super().__init__(self._content(step), classes='steering')

    def show(self, step: chat_items.SteeringStep) -> None:
        """Updates the view.

        Args:
            step (chat_items.SteeringStep): The steering step, perhaps with a new outcome.
        """
        self.update(self._content(step))

    def _content(self, step: chat_items.SteeringStep) -> Content:
        """The view's text.

        Args:
            step (chat_items.SteeringStep): The steering step.

        Returns:
            Content: Who sent it and when, the message, and its outcome.
        """
        message = step.message
        return Content.from_markup(
            '[b]You, while it worked[/b] [dim]$time[/dim]\n$text\n[dim]$status[/dim]',
            time=formatter.Formatter().time(message.received_at),
            text=message.text,
            status=message.status_text(),
        )
