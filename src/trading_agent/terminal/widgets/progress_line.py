"""The live line above the message box while a trader works, as in Claude Code.

It shows a turning spark, words saying what the trader is doing, the tool's most telling argument, and the time so far. The words follow the web page's TurnProgress.tsx: "Waiting in the queue", the running tool's activity, "Writing the answer", or a thinking word that stays the same for the whole turn.

Typical usage example:

  line = ProgressLine()
  line.follow(turn)
  line.follow(None)
"""

import datetime

from textual import widgets
from textual.content import Content

from trading_agent.terminal import chat_items
from trading_agent.terminal import formatter
from trading_agent.terminal import tool_describer

_THINKING_WORDS = (
    'Thinking',
    'Pondering',
    'Reading the tape',
    'Weighing it up',
    'Mulling it over',
    'Crunching the numbers',
    'Considering',
    'Sizing it up',
)
_SPARKS = (
    '·',
    '✢',
    '✳',
    '✶',
    '✻',
    '✽',
    '✻',
    '✶',
    '✳',
    '✢',
)
_TICK_SECONDS = 0.12


class ProgressLine(widgets.Static):
    """The progress line; hidden while no turn runs."""

    def __init__(self):
        """Creates the line, hidden."""
        super().__init__('', id='progress-line')
        self._turn: chat_items.ChatTurn | None = None
        self._tick = 0
        self._formatter = formatter.Formatter()
        self._describer = tool_describer.ToolDescriber()

    def on_mount(self) -> None:
        """Starts the animation timer."""
        self.display = False
        self.set_interval(_TICK_SECONDS, self._advance)

    def follow(self, turn: chat_items.ChatTurn | None) -> None:
        """Shows the progress of a turn, or hides the line.

        Args:
            turn (chat_items.ChatTurn | None): The turn that is waiting or running, or None when the trader is idle.
        """
        self._turn = turn
        self.display = turn is not None
        self._draw()

    def _advance(self) -> None:
        """Moves the spark on and redraws."""
        if self._turn is None:
            return
        self._tick += 1
        self._draw()

    def _draw(self) -> None:
        """Redraws the line from the followed turn."""
        turn = self._turn
        if turn is None:
            self.update('')
            return
        label = self._thinking_word(turn.trigger_id)
        detail = ''
        running = turn.running_tool()
        if not turn.started:
            label = 'Waiting in the queue'
        elif running is not None:
            label = self._describer.activity(running.name)
            detail = self._describer.detail(running.arguments_text())
        elif turn.streaming_text:
            label = 'Writing the answer'
        since = self._formatter.moment(turn.started_at or turn.received_at)
        seconds = 0
        if since is not None:
            now = datetime.datetime.now(datetime.UTC)
            seconds = max(0, int((now - since).total_seconds()))
        self.update(
            Content.from_markup(
                '[$accent]$spark[/] [b]$label…[/b] [dim]$detail[/dim] [dim]($time · esc to stop)[/dim]',
                spark=_SPARKS[self._tick % len(_SPARKS)],
                label=label,
                detail=detail,
                time=self._formatter.elapsed_text(seconds),
            )
        )

    def _thinking_word(self, trigger_id: str) -> str:
        """A word for thinking, the same one for the whole turn.

        Args:
            trigger_id (str): The turn's trigger id.

        Returns:
            str: One of the thinking words.
        """
        total = 0
        for character in trigger_id:
            total += ord(character)
        return _THINKING_WORDS[total % len(_THINKING_WORDS)]
