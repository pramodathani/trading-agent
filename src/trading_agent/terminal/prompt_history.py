"""The prompts typed in the terminal program, recalled with Up and Down and searched with Ctrl+R.

Each prompt is one JSON string per line, so prompts with several lines are kept whole. The newest 1000 are kept.

Typical usage example:

  history = PromptHistory(Path('~/.local/state/trading-agent/history').expanduser())
  history.add('/status')
  history.previous('')  # '/status'
"""

import json
from pathlib import Path

_MOST_KEPT = 1000


class PromptHistory:
    """The typed prompts, oldest first, with a cursor for Up and Down."""

    def __init__(self, file: Path | None):
        """Reads the saved prompts.

        Args:
            file (Path | None): Where prompts are kept, or None to keep them only in memory.
        """
        self._file = file
        self._prompts: list[str] = []
        self._position: int | None = None
        self._draft = ''
        if file is None:
            return
        try:
            lines = file.read_text(encoding='utf-8').splitlines()
        except OSError:
            return
        for line in lines:
            try:
                prompt = json.loads(line)
            except ValueError:
                continue
            if isinstance(prompt, str) and prompt:
                self._prompts.append(prompt)
        self._prompts = self._prompts[-_MOST_KEPT:]

    def add(self, prompt: str) -> None:
        """Records a sent prompt, unless it repeats the newest one.

        Args:
            prompt (str): The prompt.
        """
        self._position = None
        self._draft = ''
        if not prompt.strip():
            return
        if self._prompts and self._prompts[-1] == prompt:
            return
        self._prompts.append(prompt)
        self._prompts = self._prompts[-_MOST_KEPT:]
        self._save()

    def previous(self, current: str) -> str | None:
        """Moves one prompt back.

        Args:
            current (str): What is in the input box now; kept as the draft when leaving it.

        Returns:
            str | None: The older prompt, or None at the oldest.
        """
        if not self._prompts:
            return None
        if self._position is None:
            self._draft = current
            self._position = len(self._prompts)
        if self._position == 0:
            return None
        self._position -= 1
        return self._prompts[self._position]

    def next(self) -> str | None:
        """Moves one prompt forward.

        Returns:
            str | None: The newer prompt, the draft after the newest, or None when not browsing.
        """
        if self._position is None:
            return None
        self._position += 1
        if self._position >= len(self._prompts):
            self._position = None
            return self._draft
        return self._prompts[self._position]

    def search(self, words: str) -> list[str]:
        """The prompts that contain some text, newest first, each once.

        Args:
            words (str): The text to look for, ignoring case.

        Returns:
            list[str]: The matching prompts.
        """
        wanted = words.lower()
        found = []
        for prompt in reversed(self._prompts):
            if wanted in prompt.lower() and prompt not in found:
                found.append(prompt)
        return found

    def _save(self) -> None:
        """Writes the prompts, ignoring a folder that cannot be written."""
        if self._file is None:
            return
        lines = []
        for prompt in self._prompts:
            lines.append(json.dumps(prompt, ensure_ascii=False))
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        except OSError:
            return
