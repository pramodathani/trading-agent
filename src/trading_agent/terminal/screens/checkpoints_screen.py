"""The Checkpoints page: snapshots of a desk's own files, with restore.

It copies the web page's CheckpointsPage.tsx. Restoring puts the desk's Memory.md, memory/ and notes/ back as they were; the gateway first takes a checkpoint of the present state, so a restore can be undone. The newest checkpoint is the present state and cannot be restored.

Typical usage example:

  app.push_screen(CheckpointsScreen('general'))
"""

from typing import Any, ClassVar

from textual import binding
from textual import widgets
from textual import work

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen
from trading_agent.terminal.widgets import confirm_dialog


class CheckpointsScreen(page_screen.PageScreen):
    """The Checkpoints page."""

    TITLE_TEXT = 'Checkpoints'
    PER_DESK = True

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('d', 'next_desk', 'Next desk'),
        binding.Binding('s', 'restore', 'Restore'),
    ]

    def __init__(self, desk_name: str):
        """Creates the page.

        Args:
            desk_name (str): The desk the chat shows.
        """
        super().__init__(desk_name)
        self._checkpoints: list[dict[str, Any]] = []
        self._formatter = formatter.Formatter()

    def compose_page(self):
        """Builds the checkpoints table.

        Yields:
            Widget: The note and the table.
        """
        yield widgets.Static(
            "[dim]Restoring puts the desk's Memory.md, memory/ and notes/ back as they were. A checkpoint of the present is taken first, so it can be undone.[/dim]",
            classes='page-summary',
        )
        yield widgets.DataTable(id='checkpoints', cursor_type='row')

    def on_mount(self) -> None:
        """Sets up the table, then reads the checkpoints."""
        self.table('checkpoints').add_columns('Taken', 'Why', 'Id')
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the desk's checkpoints."""
        try:
            answer = await self.app.gateway.checkpoints(self.desk_name)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._checkpoints = answer.get('checkpoints') or []
        table = self.table('checkpoints')
        table.clear()
        for index, checkpoint in enumerate(self._checkpoints):
            why = str(checkpoint.get('reason', ''))
            if index == 0:
                why += '  (the present state)'
            table.add_row(
                self._formatter.day_time(str(checkpoint.get('created_at', ''))),
                why,
                str(checkpoint.get('checkpoint_id', '')),
                key=str(checkpoint.get('checkpoint_id', '')),
            )

    def action_restore(self) -> None:
        """Asks for a reason, then restores the highlighted checkpoint."""
        checkpoint_id = self.selected_key('checkpoints')
        if checkpoint_id is None:
            return
        if self._checkpoints and checkpoint_id == self._checkpoints[0].get(
            'checkpoint_id'
        ):
            self.notify(
                'The newest checkpoint is the present state; choose an older one.'
            )
            return

        def restore(reason: str | None) -> None:
            """Restores once a reason is given.

            Args:
                reason (str | None): The reason, or None when cancelled.
            """
            if reason is not None:
                self._restore(checkpoint_id)

        self.app.push_screen(
            confirm_dialog.ConfirmDialog(
                f'Restore checkpoint {checkpoint_id}',
                f"{self.desk_name}'s Memory.md, memory/ and notes/ go back to how they were at this checkpoint.",
                'Restore',
            ),
            restore,
        )

    @work(group='action')
    async def _restore(self, checkpoint_id: str) -> None:
        """Restores a checkpoint and names the undo checkpoint.

        Args:
            checkpoint_id (str): The checkpoint.
        """
        try:
            answer = await self.app.gateway.restore_checkpoint(
                self.desk_name, checkpoint_id
            )
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify(
            f'Restored {answer.get("restored")}. To undo, restore {answer.get("undo_checkpoint_id")}.',
            timeout=15,
        )
        self.refresh_page()
