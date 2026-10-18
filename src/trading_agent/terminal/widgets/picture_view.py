"""A picture in the chat: one a tool showed the model, one the desk sent, or one the user attached.

The picture is downloaded from the gateway and drawn with textual-image, which uses the terminal's own graphics (the Kitty protocol or Sixel) when it has them, and coloured half-blocks otherwise. Enter, or a click, opens the full picture with the desktop's default program.

Typical usage example:

  view = PictureView('general', picture_path='charts/nifty.png')
  view = PictureView('general', attachment=attachment)
"""

import io
from pathlib import Path
from typing import Any, ClassVar

import PIL.Image
from textual import binding
from textual import containers
from textual import events
from textual import widgets
from textual import work
from textual.content import Content
from textual_image import widget as image_widget

from trading_agent.terminal import gateway_client


class PictureView(containers.Vertical):
    """A picture with its name."""

    can_focus = True

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('enter', 'open_picture', 'Open', show=False),
    ]

    def __init__(
        self,
        desk_name: str,
        picture_path: str | None = None,
        attachment: dict[str, Any] | None = None,
    ):
        """Creates the view; the picture loads once it is on screen.

        Args:
            desk_name (str): The desk the picture belongs to.
            picture_path (str | None): A picture inside the desk's folder, from a tool result.
            attachment (dict[str, Any] | None): An attachment, from a message.
        """
        super().__init__(classes='picture')
        self._desk_name = desk_name
        self._picture_path = picture_path
        self._attachment = attachment
        self._saved: Path | None = None
        self._caption = widgets.Static(
            Content.from_markup(
                '[dim]▨ $name · loading…[/dim]', name=self._file_name()
            ),
            classes='picture-caption',
        )

    def compose(self):
        """Builds the view.

        Yields:
            Widget: The caption; the picture is added once loaded.
        """
        yield self._caption

    def on_mount(self) -> None:
        """Starts loading the picture."""
        self._load()

    def on_click(self, event: events.Click) -> None:
        """Opens the picture on a click.

        Args:
            event (events.Click): The click.
        """
        del event
        self.action_open_picture()

    def action_open_picture(self) -> None:
        """Opens the full picture with the desktop's default program."""
        if self._saved is None:
            self.notify('The picture has not loaded yet.', timeout=3)
            return
        if not self.app.opener.open(self._saved):
            self.notify(
                f'Saved to {self._saved}', title='xdg-open is not installed'
            )

    @work(group='picture')
    async def _load(self) -> None:
        """Downloads the picture and draws it."""
        opener = self.app.opener
        try:
            if self._attachment is not None:
                self._saved = await opener.save_attachment(
                    self._desk_name, self._attachment
                )
            else:
                self._saved = await opener.save_picture(
                    self._desk_name, self._picture_path or ''
                )
            picture = PIL.Image.open(io.BytesIO(self._saved.read_bytes()))
            picture.load()
        except (
            gateway_client.GatewayError,
            OSError,
            PIL.UnidentifiedImageError,
        ) as error:
            self._caption.update(
                Content.from_markup(
                    '[$error]▨ $name could not be shown: $error_text[/]',
                    name=self._file_name(),
                    error_text=str(error),
                )
            )
            return
        await self.mount(image_widget.Image(picture, classes='picture-image'))
        self._caption.update(
            Content.from_markup(
                '[dim]▨ $name · enter or click to open[/dim]',
                name=self._file_name(),
            )
        )

    def _file_name(self) -> str:
        """The picture's file name.

        Returns:
            str: The attachment's name, or the last part of the picture path.
        """
        if self._attachment is not None:
            return str(self._attachment.get('file_name', 'picture'))
        return (self._picture_path or 'picture').split('/')[-1]
