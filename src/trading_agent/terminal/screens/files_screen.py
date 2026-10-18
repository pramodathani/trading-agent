"""The Files page: the user's editable files, with an editor, and the changes desks propose to them.

It copies the web page's FilesPage.tsx. A file opens in an editor; Ctrl+S saves it and Ctrl+U puts back the text as it was last saved. Leaving a file with unsaved changes asks first. Proposals show their diff and are accepted with a or rejected with x.

Typical usage example:

  app.push_screen(FilesScreen('general'))
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import screen
from textual import widgets
from textual import work
from textual.content import Content
from textual.widgets import option_list

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen
from trading_agent.terminal.widgets import diff_view


class FilesScreen(page_screen.PageScreen):
    """The Files page."""

    TITLE_TEXT = 'Files'

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('ctrl+s', 'save', 'Save the file'),
        binding.Binding('ctrl+u', 'revert', 'Put back the saved text'),
        binding.Binding('a', 'accept', 'Accept proposal'),
        binding.Binding('x', 'reject', 'Reject proposal'),
        binding.Binding('h', 'toggle_decided', 'Show decided proposals'),
    ]

    def __init__(self, desk_name: str):
        """Creates the page.

        Args:
            desk_name (str): The desk the chat shows.
        """
        super().__init__(desk_name)
        self._files: list[dict[str, Any]] = []
        self._proposals: list[dict[str, Any]] = []
        self._shown_proposals: list[dict[str, Any]] = []
        self._show_decided = False
        self._open_file: dict[str, Any] | None = None
        self._saved_text = ''
        self._open_proposal: dict[str, Any] | None = None
        self._formatter = formatter.Formatter()

    def compose_page(self):
        """Builds the file and proposal lists and the editor and diff panes.

        Yields:
            Widget: The page's parts.
        """
        with containers.Horizontal(classes='page-columns'):
            with containers.Vertical(classes='page-left'):
                yield widgets.Static('[b]Files[/b]', classes='page-heading')
                yield widgets.OptionList(id='files-list')
                yield widgets.Static(
                    '', id='proposals-heading', classes='page-heading'
                )
                yield widgets.OptionList(id='proposals-list')
            with containers.Vertical(classes='page-right'):
                yield widgets.Static(
                    '[dim]Choose a file or a proposal on the left.[/dim]',
                    id='files-right-title',
                )
                yield widgets.TextArea(
                    '',
                    id='files-editor',
                    language='markdown',
                    show_line_numbers=True,
                )
                with containers.VerticalScroll(id='files-diff-scroll'):
                    yield diff_view.DiffView(id='files-diff')

    def on_mount(self) -> None:
        """Hides the editor and the diff until something is chosen."""
        self.query_one('#files-editor').display = False
        self.query_one('#files-diff-scroll').display = False
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the files and the proposals."""
        gateway = self.app.gateway
        try:
            files = await gateway.files()
            proposals = await gateway.proposals()
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._files = files.get('files') or []
        self._proposals = proposals.get('proposals') or []
        listing = self.query_one('#files-list', widgets.OptionList)
        listing.clear_options()
        for file in self._files:
            where = file.get('desk') or 'shared'
            size = f'{file.get("characters", 0)} characters'
            if not file.get('exists'):
                size = 'not created yet'
            listing.add_option(
                option_list.Option(
                    Content.from_markup(
                        '$name [dim]$where · $size[/dim]',
                        name=str(file.get('name', '')),
                        where=where,
                        size=size,
                    )
                )
            )
        if self._files and listing.highlighted is None:
            listing.highlighted = 0
        self._show_proposal_list()

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Opens the chosen file or proposal.

        Args:
            event (widgets.OptionList.OptionSelected): The choice.
        """
        event.stop()
        if event.option_list.id == 'files-list':
            self._ask_before_leaving(
                lambda: self._open(self._files[event.option_index])
            )
        else:
            self._ask_before_leaving(
                lambda: self._show_proposal(
                    self._shown_proposals[event.option_index]
                )
            )

    def action_save(self) -> None:
        """Saves the open file."""
        if self._open_file is not None:
            self._save()

    def action_revert(self) -> None:
        """Puts back the text as it was last saved."""
        if self._open_file is not None:
            self.query_one(
                '#files-editor', widgets.TextArea
            ).text = self._saved_text

    def action_accept(self) -> None:
        """Accepts the shown proposal, changing its file."""
        if (
            self._open_proposal is not None
            and self._open_proposal.get('status') == 'pending'
        ):
            self._decide(True)

    def action_reject(self) -> None:
        """Rejects the shown proposal."""
        if (
            self._open_proposal is not None
            and self._open_proposal.get('status') == 'pending'
        ):
            self._decide(False)

    def action_toggle_decided(self) -> None:
        """Shows or hides proposals that were already accepted or rejected."""
        self._show_decided = not self._show_decided
        self._show_proposal_list()

    def action_back(self) -> None:
        """Goes back to the chat, asking first when the open file has unsaved changes."""
        self._ask_before_leaving(self.app.pop_screen)

    @work(exclusive=True, group='file')
    async def _open(self, file: dict[str, Any]) -> None:
        """Reads a file into the editor.

        Args:
            file (dict[str, Any]): The file.
        """
        try:
            answer = await self.app.gateway.file_text(
                file.get('name', ''), file.get('desk')
            )
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._open_file = file
        self._open_proposal = None
        self._saved_text = str(answer.get('text', ''))
        editor = self.query_one('#files-editor', widgets.TextArea)
        editor.text = self._saved_text
        editor.display = True
        self.query_one('#files-diff-scroll').display = False
        where = file.get('desk') or 'shared'
        self.query_one('#files-right-title', widgets.Static).update(
            Content.from_markup(
                '[b]$name[/b] [dim]$where · ctrl+s save · ctrl+u put back the saved text[/dim]',
                name=str(file.get('name', '')),
                where=where,
            )
        )
        editor.focus()

    @work(exclusive=True, group='file')
    async def _save(self) -> None:
        """Writes the editor's text to the open file."""
        file = self._open_file or {}
        text = self.query_one('#files-editor', widgets.TextArea).text
        try:
            answer = await self.app.gateway.save_file(
                file.get('name', ''), file.get('desk'), text
            )
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self._saved_text = text
        self.notify(
            f'Saved {file.get("name")} ({answer.get("characters")} characters).',
            timeout=3,
        )
        self.refresh_page()

    @work(exclusive=True, group='file')
    async def _decide(self, accept: bool) -> None:
        """Accepts or rejects the shown proposal.

        Args:
            accept (bool): True to accept, False to reject.
        """
        proposal = self._open_proposal or {}
        try:
            await self.app.gateway.decide_proposal(
                str(proposal.get('proposal_id')), accept
            )
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        word = 'Rejected'
        if accept:
            word = 'Accepted'
        self.notify(
            f'{word} the change to {proposal.get("file_name")}.', timeout=3
        )
        self._open_proposal = None
        self.query_one('#files-diff-scroll').display = False
        self.refresh_page()

    def _show_proposal(self, proposal: dict[str, Any]) -> None:
        """Shows a proposal's reason and diff.

        Args:
            proposal (dict[str, Any]): The proposal.
        """
        self._open_proposal = proposal
        self._open_file = None
        self.query_one('#files-editor').display = False
        self.query_one('#files-diff-scroll').display = True
        keys = ''
        if proposal.get('status') == 'pending':
            keys = ' · a accept · x reject'
        self.query_one('#files-right-title', widgets.Static).update(
            Content.from_markup(
                '[b]$file[/b] [dim]from $desk, $status$keys[/dim]\n$reason',
                file=str(proposal.get('file_name', '')),
                desk=str(proposal.get('desk', '')),
                status=str(proposal.get('status', '')),
                keys=keys,
                reason=str(proposal.get('reason', '')),
            )
        )
        self.query_one('#files-diff', diff_view.DiffView).show(
            str(proposal.get('difference', ''))
        )

    def _show_proposal_list(self) -> None:
        """Redraws the proposals list, pending first."""
        pending = 0
        self._shown_proposals = []
        for proposal in self._proposals:
            if proposal.get('status') == 'pending':
                pending += 1
                self._shown_proposals.append(proposal)
        if self._show_decided:
            for proposal in self._proposals:
                if proposal.get('status') != 'pending':
                    self._shown_proposals.append(proposal)
        shown_word = 'h shows decided ones'
        if self._show_decided:
            shown_word = 'h hides decided ones'
        self.query_one('#proposals-heading', widgets.Static).update(
            Content.from_markup(
                '[b]Proposals[/b] [dim]$pending pending · $word[/dim]',
                pending=str(pending),
                word=shown_word,
            )
        )
        listing = self.query_one('#proposals-list', widgets.OptionList)
        listing.clear_options()
        for proposal in self._shown_proposals:
            listing.add_option(
                option_list.Option(
                    Content.from_markup(
                        '$file [dim]$desk · $status · $when[/dim]',
                        file=str(proposal.get('file_name', '')),
                        desk=str(proposal.get('desk', '')),
                        status=str(proposal.get('status', '')),
                        when=self._formatter.day_time(
                            str(proposal.get('created_at', ''))
                        ),
                    )
                )
            )
        if self._shown_proposals:
            listing.highlighted = 0

    def _ask_before_leaving(self, then: Any) -> None:
        """Runs an action, first asking to discard unsaved changes of the open file.

        Args:
            then (Any): What to do once allowed; called with no arguments.
        """
        if self._open_file is None:
            then()
            return
        editor = self.query_one('#files-editor', widgets.TextArea)
        if editor.text == self._saved_text:
            then()
            return

        def decided(discard: bool | None) -> None:
            """Goes on when the user chose to discard.

            Args:
                discard (bool | None): True to discard the changes.
            """
            if discard:
                self._saved_text = editor.text
                then()

        self.app.push_screen(
            DiscardDialog(str(self._open_file.get('name', ''))), decided
        )


class DiscardDialog(screen.ModalScreen[bool]):
    """Asks whether to discard unsaved changes to a file."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('y', 'discard', 'Discard'),
        binding.Binding('n,escape', 'keep', 'Keep editing'),
    ]

    def __init__(self, file_name: str):
        """Creates the dialog.

        Args:
            file_name (str): The file with unsaved changes.
        """
        super().__init__(classes='picker-screen')
        self._file_name = file_name

    def compose(self):
        """Builds the dialog.

        Yields:
            Widget: The question and the keys.
        """
        with containers.Vertical(classes='picker'):
            yield widgets.Static(
                Content.from_markup(
                    '[b]$name has unsaved changes.[/b]\nDiscard them?',
                    name=self._file_name,
                )
            )
            yield widgets.Static(
                '[dim]y discard · n keep editing[/dim]', classes='picker-hint'
            )

    def action_discard(self) -> None:
        """Discards the changes."""
        self.dismiss(True)

    def action_keep(self) -> None:
        """Keeps editing."""
        self.dismiss(False)
