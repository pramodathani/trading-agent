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

from trading_agent.skills import skill_library as skill_library_module
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
        skill_library: skill_library_module.SkillLibrary | None = None,
    ):
        """Creates the builder.

        Args:
            layout (workspace_layout.WorkspaceLayout): Where the files are.
            desk_name (str): The desk the prompt is for.
            mode (str): "dry_run" or "live", stated in the prompt.
            skill_library (skill_library_module.SkillLibrary | None): The desk's skills, listed as an index at the end, or None for no index.
        """
        self._layout = layout
        self._desk_name = desk_name
        self._mode = mode
        self._skill_library = skill_library

    def build(self) -> SystemPrompt:
        """Reads the files and assembles the prompt.

        Returns:
            SystemPrompt: The prompt and its fingerprint.
        """
        sections = [
            self._header(),
            self._memory_guide(),
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
        if self._skill_library is not None:
            sections.append(self._skill_library.index_text())
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
                'After a note on how your memory works, the files below are your instructions, in this order: how every desk works, your persona, the user, the trading rules, and your own memory. An index of your skills comes last.',
            ]
        )

    def _memory_guide(self) -> str:
        """Explains how the desk's memory works, which is part of the code rather than of any file.

        Returns:
            str: The section.
        """
        return '\n'.join(
            [
                '===== How your memory works =====',
                '- This conversation is one session. Each India trading day starts a fresh session, whose first message carries the summary of your previous session. After a restart you continue the same session.',
                "- When a session ends you are asked to fold the day's notes into Memory.md and to summarise the session. Memory.md is your lasting knowledge: keep it short, organised and true, and remove lessons that proved wrong.",
                "- After a turn in which you learned something worth keeping, about the market, your strategy, a tool, a mistake or the user's wishes, record one to three short notes with add_note. Skip routine turns.",
                '- search_sessions finds what happened before: earlier exchanges, daily summaries, notes, and the journal of your orders and tool calls.',
                '- Every change to Memory.md, memory/ and notes/ is snapshotted first, so the user can undo it.',
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
