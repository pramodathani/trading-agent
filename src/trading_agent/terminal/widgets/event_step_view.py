"""An event shown inside a turn or on its own, such as a risk decision, an order or a fill.

Typical usage example:

  view = EventStepView(event)
"""

from typing import Any

from textual import widgets
from textual.content import Content

from trading_agent.terminal import event_describer
from trading_agent.terminal import formatter

_MOST_DETAIL_CHARACTERS = 600


class EventStepView(widgets.Static):
    """One event as a line in its tone's colour, with its detail below."""

    def __init__(self, event: dict[str, Any], with_time: bool = False):
        """Creates the line.

        Args:
            event (dict[str, Any]): The event.
            with_time (bool): Whether to start with the event's India clock time, for events outside turns.
        """
        description = event_describer.EventDescriber().describe(event)
        super().__init__(
            self._content(event, description, with_time),
            classes=f'event-step tone-{description.tone}',
        )

    def _content(
        self,
        event: dict[str, Any],
        description: event_describer.EventDescription,
        with_time: bool,
    ) -> Content:
        """The line's text.

        Args:
            event (dict[str, Any]): The event.
            description (event_describer.EventDescription): Its title, detail and tone.
            with_time (bool): Whether to start with the time.

        Returns:
            Content: The title, and the shortened detail on the following lines.
        """
        detail = description.detail
        if len(detail) > _MOST_DETAIL_CHARACTERS:
            detail = detail[: _MOST_DETAIL_CHARACTERS - 1] + '…'
        time_text = ''
        if with_time:
            time_text = formatter.Formatter().time(event.get('created_at', ''))
        markup = '● [b]$title[/b]'
        if with_time:
            markup = '[dim]$time[/dim]  ● [b]$title[/b]'
        if detail:
            markup += '\n[dim]$detail[/dim]'
        return Content.from_markup(
            markup,
            time=time_text,
            title=description.title,
            detail=detail,
        )
