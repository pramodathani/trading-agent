"""The side panel's Outputs card: pictures and documents the desk sent today, newest first.

Choosing one downloads it and opens it with the desktop's default program.

Typical usage example:

  card = OutputsCard(opener)
  card.show('general', events)
"""

from collections.abc import Sequence
from typing import Any

from textual import widgets
from textual import work
from textual.content import Content
from textual.widgets import option_list

from trading_agent.terminal import attachment_opener
from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.widgets import side_card


class OutputsCard(side_card.SideCard):
    """The Outputs card."""

    def __init__(
        self,
        opener: attachment_opener.AttachmentOpener,
        collapsed: bool = False,
    ):
        """Creates the card.

        Args:
            opener (attachment_opener.AttachmentOpener): Downloads and opens the files.
            collapsed (bool): Whether it starts folded.
        """
        self._list = widgets.OptionList(classes='output-list')
        super().__init__('outputs', 'Outputs', self._list, collapsed=collapsed)
        self._opener = opener
        self._formatter = formatter.Formatter()
        self._outputs: list[dict[str, Any]] = []
        self._desk_name = ''

    def show(self, desk_name: str, events: Sequence[dict[str, Any]]) -> None:
        """Lists the files in the desk's messages of today.

        Args:
            desk_name (str): The desk.
            events (Sequence[dict[str, Any]]): The desk's events of today.
        """
        self._desk_name = desk_name
        outputs = []
        for event in events:
            if event.get('kind') != 'message':
                continue
            attachments = (event.get('payload') or {}).get('attachments')
            if not isinstance(attachments, list):
                continue
            for attachment in attachments:
                outputs.append(
                    {
                        'attachment': attachment,
                        'sent_at': event.get('created_at', ''),
                    }
                )
        outputs.reverse()
        if [item['attachment'].get('attachment_id') for item in outputs] == [
            item['attachment'].get('attachment_id') for item in self._outputs
        ]:
            return
        self._outputs = outputs
        self.show_aside(str(len(outputs)))
        if not outputs:
            self.show_body(
                self.note('Pictures and documents the desk sends appear here.')
            )
        else:
            self.show_body(self.note('Enter opens one in its own program.'))
        self._list.clear_options()
        for output in outputs:
            attachment = output['attachment']
            icon = '▣'
            if attachment.get('kind') == 'image':
                icon = '▨'
            self._list.add_option(
                option_list.Option(
                    Content.from_markup(
                        '$icon $name [dim]$time[/dim]',
                        icon=icon,
                        name=str(attachment.get('file_name', 'file')),
                        time=self._formatter.time(output['sent_at'])[:5],
                    )
                )
            )
        self._list.display = bool(outputs)

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Opens the chosen file.

        Args:
            event (widgets.OptionList.OptionSelected): The choice.
        """
        event.stop()
        self._open(self._outputs[event.option_index]['attachment'])

    @work(group='open')
    async def _open(self, attachment: dict[str, Any]) -> None:
        """Downloads a file and opens it.

        Args:
            attachment (dict[str, Any]): The attachment.
        """
        try:
            path = await self._opener.save_attachment(
                self._desk_name, attachment
            )
        except (gateway_client.GatewayError, OSError) as error:
            self.notify(str(error), title='Could not open', severity='error')
            return
        if not self._opener.open(path):
            self.notify(f'Saved to {path}', title='xdg-open is not installed')
            return
        self.notify(f'Opened {path.name}', timeout=3)
