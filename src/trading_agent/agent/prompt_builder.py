"""Builds a desk's system prompt from the workspace files.

The prompt is read fresh before every turn, so an edit to a file reaches the desk on its next turn. It holds only slow-changing text, so that it stays identical between turns and the model's prompt cache keeps working; the time and the trigger go in the user message instead.

Typical usage example:

  builder = PromptBuilder(layout, 'main', 'dry_run')
  prompt = builder.build()
  prompt.text, prompt.fingerprint
"""

import dataclasses
import hashlib
from pathlib import Path

from trading_agent.workspace import workspace_layout

MAXIMUM_FILE_CHARACTERS = 20000
MAXIMUM_TOTAL_CHARACTERS = 60000


@dataclasses.dataclass(frozen=True)
class SystemPrompt:
    """One built prompt.

    Attributes:
        text: The prompt.
        fingerprint: A short hash of the text, which changes whenever the text does.
    """

    text: str
    fingerprint: str


class PromptBuilder:
    """Assembles one desk's prompt."""

    def __init__(
        self,
        layout: workspace_layout.WorkspaceLayout,
        desk_name: str,
        mode: str,
    ):
        """Creates the builder.

        Args:
            layout (workspace_layout.WorkspaceLayout): Where the files are.
            desk_name (str): The desk the prompt is for.
            mode (str): "dry_run" or "live", stated in the prompt.
        """
        self._layout = layout
        self._desk_name = desk_name
        self._mode = mode

    def build(self) -> SystemPrompt:
        """Reads the files and assembles the prompt.

        Returns:
            SystemPrompt: The prompt and its fingerprint.
        """
        sections = [
            self._header(),
            self._section('Agents.md', self._layout.agents_file),
            self._section(
                'Persona.md', self._layout.persona_file(self._desk_name)
            ),
            self._section('User.md', self._layout.user_file),
            self._section('TradingRules.md', self._layout.trading_rules_file),
            self._section(
                'Memory.md', self._layout.memory_file(self._desk_name)
            ),
        ]
        if self._layout.is_template(self._layout.user_file):
            sections.append(self._layout.template_text('FirstRunInterview.md'))
        text = '\n\n'.join(sections)
        if len(text) > MAXIMUM_TOTAL_CHARACTERS:
            text = (
                text[:MAXIMUM_TOTAL_CHARACTERS]
                + '\n\n[The workspace files were cut here because together they exceed 60,000 characters.]'
            )
        fingerprint = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
        return SystemPrompt(text=text, fingerprint=fingerprint)

    def _header(self) -> str:
        """States which desk this is and whether orders are real.

        Returns:
            str: The prompt's opening lines.
        """
        if self._mode == 'live':
            mode_line = (
                'Mode: live. Orders reach the exchange and use real money.'
            )
        else:
            mode_line = 'Mode: dry_run. Orders go to UBI as dry runs and never reach the exchange.'
        return '\n'.join(
            [
                f'You are the "{self._desk_name}" desk of trading-agent.',
                mode_line,
                'The files below are your instructions, in this order: how every desk works, your persona, the user, the trading rules, and your own memory.',
            ]
        )

    def _section(self, title: str, path: Path) -> str:
        """Reads one file as a titled section, capped in length.

        Args:
            title (str): The section's title.
            path (Path): The file.

        Returns:
            str: The section, or a note that the file is missing.
        """
        if not path.is_file():
            return f'===== {title} =====\n[missing: {path}]'
        text = path.read_text(encoding='utf-8')
        if len(text) > MAXIMUM_FILE_CHARACTERS:
            text = (
                text[:MAXIMUM_FILE_CHARACTERS]
                + f'\n[{title} was cut here because it exceeds 20,000 characters.]'
            )
        return f'===== {title} =====\n{text}'
