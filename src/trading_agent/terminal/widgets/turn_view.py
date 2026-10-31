"""One turn in the chat: what woke the trader, its steps, the text it is writing, and its answer.

The steps of a turn are only ever added at the end, and only the last tool run grows, so the view updates its step views by position and mounts views for new ones.

Typical usage example:

  view = TurnView(turn)
  view.show(turn)
"""

from typing import Any

from textual import containers
from textual import widgets
from textual.content import Content

from trading_agent.terminal import chat_items
from trading_agent.terminal import event_describer
from trading_agent.terminal import formatter
from trading_agent.terminal.widgets import event_step_view
from trading_agent.terminal.widgets import picture_view
from trading_agent.terminal.widgets import request_step_view
from trading_agent.terminal.widgets import steering_view
from trading_agent.terminal.widgets import tool_run_view
from trading_agent.terminal.widgets import trader_message_view


class TurnView(containers.Vertical):
    """A turn's view.

    Attributes:
        trigger_id: The trigger the turn belongs to.
    """

    def __init__(self, trader_name: str, turn: chat_items.ChatTurn):
        """Creates the view.

        Args:
            trader_name (str): The trader the turn belongs to, for its pictures.
            turn (chat_items.ChatTurn): The turn.
        """
        super().__init__(classes='turn')
        self.trigger_id = turn.trigger_id
        self._trader_name = trader_name
        self._user_pictures = containers.Vertical(classes='turn-pictures')
        self._shown_user_pictures: set[str] = set()
        self._turn = turn
        self._formatter = formatter.Formatter()
        self._heading = widgets.Static('', classes='turn-heading')
        self._message = widgets.Static('', markup=False, classes='turn-message')
        self._steps = containers.Vertical(classes='turn-steps')
        self._writing = widgets.Markdown('', classes='turn-writing')
        self._answer = widgets.Markdown('', classes='turn-answer')
        self._plain_answer = widgets.Static(
            '', markup=False, classes='turn-answer plain'
        )
        self._error = widgets.Static('', markup=False, classes='turn-error')
        self._status = widgets.Static('', classes='turn-status')
        self._step_views: list[Any] = []
        self._shown_writing = ''
        self._shown_answer: str | None = None

    def compose(self):
        """Builds the view's parts.

        Yields:
            Widget: The heading, message, steps, writing, answer (as Markdown, or as plain text for a /command's reply), error and status.
        """
        yield self._heading
        yield self._message
        yield self._user_pictures
        yield self._steps
        yield self._writing
        yield self._answer
        yield self._plain_answer
        yield self._error
        yield self._status

    def on_mount(self) -> None:
        """Fills the view once it is on screen."""
        self.show(self._turn)

    def show(self, turn: chat_items.ChatTurn) -> None:
        """Updates the view from the turn.

        Args:
            turn (chat_items.ChatTurn): The turn, perhaps with more steps, text or an answer.
        """
        self._turn = turn
        from_user = turn.source == 'user_message'
        self.set_class(from_user, 'from-user')
        self._heading.update(self._heading_content(turn))
        self._message.update(self._message_text(turn))
        self._message.display = bool(self._message_text(turn))
        self._show_user_pictures(turn)
        self._show_steps(turn)
        writing = turn.streaming_text
        if turn.answer is not None:
            writing = ''
        if writing != self._shown_writing:
            self._shown_writing = writing
            self._writing.update(writing)
        self._writing.display = bool(writing)
        answer = turn.answer
        if turn.silent:
            answer = None
        plain = turn.text.strip().startswith('/')
        if answer != self._shown_answer:
            self._shown_answer = answer
            if plain:
                self._plain_answer.update(answer or '')
            else:
                self._answer.update(answer or '')
        self._answer.display = bool(answer) and not plain
        self._plain_answer.display = bool(answer) and plain
        self._error.update(f'The turn failed: {turn.error}')
        self._error.display = turn.error is not None
        self._status.update(self._status_content(turn))

    def expand_tools(self, expanded: bool) -> None:
        """Opens or folds every tool run of the turn.

        Args:
            expanded (bool): True to open, False to fold.
        """
        for view in self._step_views:
            if isinstance(view, tool_run_view.ToolRunView):
                view.expand_all(expanded)

    def _show_steps(self, turn: chat_items.ChatTurn) -> None:
        """Updates the step views and mounts views for new steps.

        Args:
            turn (chat_items.ChatTurn): The turn.
        """
        segments = turn.segments()
        for index, segment in enumerate(segments):
            if index < len(self._step_views):
                view = self._step_views[index]
                if isinstance(
                    view,
                    (
                        event_step_view.EventStepView,
                        trader_message_view.TraderMessageView,
                    ),
                ):
                    continue
                view.show(segment)
                continue
            view = self._new_step_view(segment)
            self._step_views.append(view)
            self._steps.mount(view)

    def _new_step_view(self, segment: Any) -> Any:
        """Creates the view of one step.

        Args:
            segment (Any): A tool run, event, steering or request step.

        Returns:
            Any: Its view.
        """
        if isinstance(segment, chat_items.ToolRun):
            return tool_run_view.ToolRunView(self._trader_name, segment)
        if isinstance(segment, chat_items.SteeringStep):
            return steering_view.SteeringView(segment)
        if isinstance(segment, chat_items.RequestStep):
            return request_step_view.RequestStepView(segment)
        if segment.event.get('kind') == 'message':
            return trader_message_view.TraderMessageView(
                self._trader_name, segment.event
            )
        return event_step_view.EventStepView(segment.event)

    def _show_user_pictures(self, turn: chat_items.ChatTurn) -> None:
        """Draws the pictures the user attached, once each.

        Args:
            turn (chat_items.ChatTurn): The turn.
        """
        for attachment in turn.attachments:
            attachment_id = str(attachment.get('attachment_id', ''))
            if attachment.get('kind') != 'image':
                continue
            if attachment_id in self._shown_user_pictures:
                continue
            self._shown_user_pictures.add(attachment_id)
            self._user_pictures.mount(
                picture_view.PictureView(
                    self._trader_name, attachment=attachment
                )
            )

    def _heading_content(self, turn: chat_items.ChatTurn) -> Content:
        """The line above the message: who or what woke the trader, and when.

        Args:
            turn (chat_items.ChatTurn): The turn.

        Returns:
            Content: Such as "You  10:04:31".
        """
        who = 'You'
        if turn.request_id is not None:
            who = 'Your response went to the trader'
        elif turn.source != 'user_message':
            who = event_describer.EventDescriber().source_words(turn.source)
        return Content.from_markup(
            '[b]$who[/b]  [dim]$time[/dim]',
            who=who,
            time=self._formatter.time(turn.received_at),
        )

    def _message_text(self, turn: chat_items.ChatTurn) -> str:
        """The trigger's text, with the names of attached files.

        Args:
            turn (chat_items.ChatTurn): The turn.

        Returns:
            str: The text, or an empty string for an answer to a request.
        """
        if turn.request_id is not None:
            return ''
        lines = []
        if turn.text:
            lines.append(turn.text)
        for attachment in turn.attachments:
            if attachment.get('kind') != 'image':
                lines.append(f'📎 {attachment.get("file_name", "file")}')
        return '\n'.join(lines)

    def _status_content(self, turn: chat_items.ChatTurn) -> Content:
        """The turn's status line.

        Args:
            turn (chat_items.ChatTurn): The turn.

        Returns:
            Content: Such as "answered by claude · 12s", or "Nothing to do" for a silent answer.
        """
        status = turn.status_text()
        if turn.silent and turn.finished:
            status = f'nothing to do · {status}'
        moment_from = self._formatter.moment(turn.started_at or '')
        moment_to = self._formatter.moment(turn.finished_at or '')
        if moment_from is not None and moment_to is not None:
            seconds = int((moment_to - moment_from).total_seconds())
            status = f'{status} · {self._formatter.elapsed_text(seconds)}'
        return Content.from_markup('[dim]$status[/dim]', status=status)
