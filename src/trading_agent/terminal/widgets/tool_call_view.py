"""One tool call, folded to a line with its name and state, opening to its arguments and result.

Typical usage example:

  view = ToolCallView(step)
  view.show(step)
"""

from textual import containers
from textual import widgets
from textual.content import Content

from trading_agent.terminal import chat_items
from trading_agent.terminal import tool_describer

_MOST_RESULT_CHARACTERS = 6000


class ToolCallView(widgets.Collapsible):
    """A tool call's card."""

    def __init__(self, step: chat_items.ToolStep):
        """Creates the card.

        Args:
            step (chat_items.ToolStep): The tool call.
        """
        self._arguments = widgets.Static(
            step.arguments_text(), markup=False, classes='tool-arguments'
        )
        self._result = widgets.Static('', markup=False, classes='tool-result')
        self._step = step
        super().__init__(
            containers.Vertical(
                widgets.Static('Arguments', classes='tool-heading'),
                self._arguments,
                widgets.Static('Result', classes='tool-heading'),
                self._result,
                classes='tool-body',
            ),
            title=self._title_content(step),
            collapsed=True,
            classes='tool-call',
        )

    def on_mount(self) -> None:
        """Fills the card once it is on screen."""
        self.show(self._step)

    def show(self, step: chat_items.ToolStep) -> None:
        """Updates the card from the tool call.

        Args:
            step (chat_items.ToolStep): The tool call, perhaps now with its result.
        """
        self._step = step
        self.title = self._title_content(step)
        result = step.result_text
        if result is None and step.ended_early:
            result = 'No result: the turn ended before the tool answered.'
        elif result is None:
            result = 'running…'
        elif len(result) > _MOST_RESULT_CHARACTERS:
            result = (
                result[:_MOST_RESULT_CHARACTERS]
                + f'\n… {len(result) - _MOST_RESULT_CHARACTERS} more characters'
            )
        self._result.update(result)
        self.set_class(step.is_error, 'failed')

    def _title_content(self, step: chat_items.ToolStep) -> Content:
        """The card's folded line.

        Args:
            step (chat_items.ToolStep): The tool call.

        Returns:
            Content: The tool's name, its most telling argument and its state.
        """
        state = 'done'
        if step.result_text is None and step.ended_early:
            state = 'ended early'
        elif step.result_text is None:
            state = 'running…'
        elif step.is_error:
            state = 'failed'
        detail = tool_describer.ToolDescriber().detail(step.arguments_text())
        return Content.from_markup(
            '[b]$name[/b] · [dim]$detail[/dim] · $state',
            name=tool_describer.ToolDescriber().base_name(step.name),
            detail=detail,
            state=state,
        )
