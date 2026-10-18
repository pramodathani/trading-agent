"""A dialog that asks for a reason, and sometimes a typed word, before a serious action such as flattening a desk or firing the kill switch.

It copies the web page's ConfirmDialog.tsx: the action cannot be confirmed until a reason is written, and, when a word is required, until that exact word is typed. It returns the reason, or None when cancelled.

Typical usage example:

  app.push_screen(ConfirmDialog('Fire the kill switch', explanation, 'Fire', word='FLATTEN'), on_reason)
"""

from typing import ClassVar

from textual import binding
from textual import containers
from textual import screen
from textual import widgets
from textual.content import Content


class ConfirmDialog(screen.ModalScreen[str | None]):
    """The confirmation dialog."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape', 'cancel', 'Cancel'),
    ]

    def __init__(
        self,
        title: str,
        explanation: str,
        action_label: str,
        word: str | None = None,
    ):
        """Creates the dialog.

        Args:
            title (str): What is about to happen.
            explanation (str): What it does, in a sentence or two.
            action_label (str): The word for confirming, such as "Flatten".
            word (str | None): A word the user must type to confirm, or None.
        """
        super().__init__(classes='picker-screen')
        self._title_text = title
        self._explanation = explanation
        self._action_label = action_label
        self._word = word

    def compose(self):
        """Builds the dialog.

        Yields:
            Widget: The title, the explanation, the reason box, the word box when needed, the error line and the hint.
        """
        with containers.Vertical(classes='picker confirm'):
            yield widgets.Static(
                Content.from_markup(
                    '[b $error]$title[/]', title=self._title_text
                ),
                classes='picker-title',
            )
            yield widgets.Static(self._explanation, markup=False)
            yield widgets.Input(
                placeholder='Reason (required, kept in the journal)',
                id='confirm-reason',
            )
            if self._word is not None:
                yield widgets.Input(
                    placeholder=f'Type {self._word} to confirm',
                    id='confirm-word',
                )
            yield widgets.Static('', id='confirm-error')
            yield widgets.Static(
                Content.from_markup(
                    '[dim]enter to $action · esc to cancel[/dim]',
                    action=self._action_label.lower(),
                ),
                classes='picker-hint',
            )

    def on_mount(self) -> None:
        """Puts the cursor in the reason box."""
        self.query_one('#confirm-reason', widgets.Input).focus()

    def on_input_submitted(self, event: widgets.Input.Submitted) -> None:
        """Confirms when the reason, and the word if needed, are given.

        Args:
            event (widgets.Input.Submitted): The submission.
        """
        event.stop()
        reason = self.query_one('#confirm-reason', widgets.Input).value.strip()
        if not reason:
            self._error('Write a reason first.')
            self.query_one('#confirm-reason', widgets.Input).focus()
            return
        if self._word is not None:
            box = self.query_one('#confirm-word', widgets.Input)
            if box.value.strip() != self._word:
                self._error(f'Type {self._word} exactly to confirm.')
                box.focus()
                return
        self.dismiss(reason)

    def action_cancel(self) -> None:
        """Closes the dialog without confirming."""
        self.dismiss(None)

    def _error(self, text: str) -> None:
        """Shows why the dialog cannot be confirmed yet.

        Args:
            text (str): The reason.
        """
        self.query_one('#confirm-error', widgets.Static).update(
            Content.from_markup('[$error]$text[/]', text=text)
        )
