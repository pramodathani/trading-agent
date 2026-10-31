"""One subagent: a helper a trader can hand a task to, defined in a Markdown file.

The format is Claude Code's subagent format, so definitions can be shared with it. YAML frontmatter, then the subagent's instructions:

  ---
  name: news_reader
  description: Reads recent news about a company or index and reports what matters for trading.
  tools: web_search, web_fetch, search_knowledge
  model: qwen
  max_turns: 12
  timeout: 300
  ---
  You read news for a trader...

- `tools` is a comma-separated list or a YAML list. Without it the subagent gets a safe, read-only set. Order tools are given only when listed by name.
- `model` is a backend name from trading_agent.toml, a list of them in order of preference, or "inherit" for the trader's own order. Claude Code's aliases opus, sonnet and haiku mean the Claude backend with that model.
- `max_turns` and `timeout` (seconds) are trading-agent's additions; Claude Code ignores them.

Typical usage example:

  definition = SubagentParser().parse(Path('workspace/shared/agents/news_reader.md'))
"""

import dataclasses
import re
from pathlib import Path
from typing import Any

import yaml

NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
DEFAULT_MAXIMUM_TURNS = 12
DEFAULT_TIMEOUT_SECONDS = 300
MAXIMUM_TIMEOUT_SECONDS = 1800
_FRONTMATTER_PATTERN = re.compile(
    r'\A---\s*\n(.*?)\n---\s*(?:\n|\Z)', re.DOTALL
)


class SubagentFormatError(ValueError):
    """A subagent file has no frontmatter, or a field is not valid."""


@dataclasses.dataclass(frozen=True)
class SubagentDefinition:
    """One subagent.

    Attributes:
        name: The subagent's name, used by delegate_task.
        description: When to use it, shown to the trader.
        instructions: Its system prompt, the Markdown after the frontmatter.
        tool_names: The tools it asked for, or None for the default read-only set.
        models: The backends or Claude aliases it asked for, in order, or None to inherit the trader's order.
        maximum_turns: The most model calls one task may make.
        timeout_seconds: How long one task may run before it is stopped.
        path: The file it was read from.
    """

    name: str
    description: str
    instructions: str
    tool_names: tuple[str, ...] | None
    models: tuple[str, ...] | None
    maximum_turns: int
    timeout_seconds: int
    path: Path


class SubagentParser:
    """Reads subagent files."""

    def parse(self, path: Path) -> SubagentDefinition:
        """Reads one subagent file.

        Args:
            path (Path): The Markdown file.

        Returns:
            SubagentDefinition: The subagent.

        Raises:
            SubagentFormatError: The file has no frontmatter, or its name, description, model or limits are not valid.
        """
        text = path.read_text(encoding='utf-8')
        match = _FRONTMATTER_PATTERN.match(text)
        if match is None:
            raise SubagentFormatError(
                f'{path} does not start with frontmatter between two --- lines'
            )
        try:
            frontmatter = yaml.safe_load(match.group(1))
        except yaml.YAMLError as error:
            raise SubagentFormatError(
                f'{path} has frontmatter that is not valid YAML: {error}'
            ) from error
        if not isinstance(frontmatter, dict):
            raise SubagentFormatError(f'{path} frontmatter is not a mapping')
        name = str(frontmatter.get('name', path.stem)).strip()
        if not NAME_PATTERN.match(name):
            raise SubagentFormatError(
                f'Subagent name {name!r} in {path} must be lower-case letters, digits, hyphens and underscores, starting with a letter'
            )
        description = str(frontmatter.get('description', '')).strip()
        if not description:
            raise SubagentFormatError(
                f'Subagent {name} in {path} needs a description'
            )
        return SubagentDefinition(
            name=name,
            description=description,
            instructions=text[match.end() :].strip(),
            tool_names=self._names(frontmatter.get('tools')),
            models=self._models(frontmatter.get('model')),
            maximum_turns=self._whole_number(
                frontmatter.get('max_turns', DEFAULT_MAXIMUM_TURNS),
                'max_turns',
                path,
                DEFAULT_MAXIMUM_TURNS * 10,
            ),
            timeout_seconds=self._whole_number(
                frontmatter.get('timeout', DEFAULT_TIMEOUT_SECONDS),
                'timeout',
                path,
                MAXIMUM_TIMEOUT_SECONDS,
            ),
            path=path,
        )

    def _names(self, value: Any) -> tuple[str, ...] | None:
        """Reads a list of names given as a comma-separated string or a YAML list.

        Args:
            value (Any): The field's value.

        Returns:
            tuple[str, ...] | None: The names, or None when the field is absent or empty.
        """
        if value is None:
            return None
        items = []
        if isinstance(value, str):
            items = value.split(',')
        elif isinstance(value, list):
            items = [str(item) for item in value]
        names = []
        for item in items:
            item = item.strip()
            if item:
                names.append(item)
        if not names:
            return None
        return tuple(names)

    def _models(self, value: Any) -> tuple[str, ...] | None:
        """Reads the model field.

        Args:
            value (Any): The field's value.

        Returns:
            tuple[str, ...] | None: The backends or aliases in order, or None for "inherit" or no field.
        """
        names = self._names(value)
        if names is None or names == ('inherit',):
            return None
        return names

    def _whole_number(
        self,
        value: Any,
        field: str,
        path: Path,
        maximum: int,
    ) -> int:
        """Reads a positive whole number with an upper limit.

        Args:
            value (Any): The field's value.
            field (str): The field's name, for the error message.
            path (Path): The file, for the error message.
            maximum (int): The largest allowed value.

        Returns:
            int: The number.

        Raises:
            SubagentFormatError: The value is not a whole number from 1 to the maximum.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise SubagentFormatError(
                f'{field} in {path} must be a whole number'
            )
        if value < 1 or value > maximum:
            raise SubagentFormatError(
                f'{field} in {path} must be from 1 to {maximum}'
            )
        return value
