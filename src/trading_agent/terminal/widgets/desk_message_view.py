"""A message the desk sent with send_message or send_image: its text, its pictures and its documents.

Pictures are drawn in the chat; documents are listed, and Enter on one opens it with the desktop's default program.

Typical usage example:

  view = DeskMessageView('general', event)
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.widgets import picture_view


class DocumentLine(widgets.Static):
    """One document in a desk message; Enter or a click opens it."""

    can_focus = True

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('enter', 'open_document', 'Open', show=False),
    ]

    def __init__(self, desk_name: str, attachment: dict[str, Any]):
        """Creates the line.

        Args:
            desk_name (str): The desk that sent it.
            attachment (dict[str, Any]): The document.
        """
        super().__init__(
            Content.from_markup(
                '▣ [u]$name[/u] [dim]enter or click to open[/dim]',
                name=str(attachment.get('file_name', 'document')),
            ),
            classes='document-line',
        )
        self._desk_name = desk_name
        self._attachment = attachment

    def on_click(self) -> None:
        """Opens the document on a click."""
        self.action_open_document()

    def action_open_document(self) -> None:
        """Downloads the document and opens it."""
        self._open()

    @work(group='open')
    async def _open(self) -> None:
        """Downloads the document and hands it to the desktop."""
        opener = self.app.opener
        try:
            path = await opener.save_attachment(
                self._desk_name, self._attachment
            )
        except (gateway_client.GatewayError, OSError) as error:
            self.notify(str(error), title='Could not open', severity='error')
            return
        if not opener.open(path):
            self.notify(f'Saved to {path}', title='xdg-open is not installed')


class DeskMessageView(containers.Vertical):
    """A message from the desk."""

    def __init__(
        self,
        desk_name: str,
        event: dict[str, Any],
        with_time: bool = False,
    ):
        """Creates the view.

        Args:
            desk_name (str): The desk that sent it.
            event (dict[str, Any]): The message event.
            with_time (bool): Whether to show the time, for a message outside a turn.
        """
        payload = event.get('payload') or {}
        classes = 'desk-message'
        if payload.get('urgent'):
            classes += ' urgent'
        super().__init__(classes=classes)
        self._desk_name = desk_name
        self._event = event
        self._with_time = with_time

    def compose(self):
        """Builds the view.

        Yields:
            Widget: The heading, the text, the pictures and the documents.
        """
        payload = self._event.get('payload') or {}
        attachments = payload.get('attachments')
        if not isinstance(attachments, list):
            attachments = []
        pictures = []
        documents = []
        for attachment in attachments:
            if attachment.get('kind') == 'image':
                pictures.append(attachment)
            else:
                documents.append(attachment)
        heading = 'Message from the desk'
        if payload.get('urgent'):
            heading = 'Urgent message from the desk'
        elif pictures and not documents:
            heading = 'Picture from the desk'
        time_text = ''
        if self._with_time:
            time_text = formatter.Formatter().time(
                str(self._event.get('created_at', ''))
            )
        yield widgets.Static(
            Content.from_markup(
                '[b]$heading[/b] [dim]$time[/dim]',
                heading=heading,
                time=time_text,
            ),
            classes='desk-message-heading',
        )
        text = str(payload.get('text') or '')
        if text:
            yield widgets.Markdown(text)
        for attachment in pictures:
            yield picture_view.PictureView(
                self._desk_name, attachment=attachment
            )
        for attachment in documents:
            yield DocumentLine(self._desk_name, attachment)
