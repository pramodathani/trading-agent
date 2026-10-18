"""Checks that the terminal program's classes do not overwrite attributes Textual itself uses.

A widget that stored its own data in `self._context` replaced Textual's `_context` method, which stopped the widget's message loop and froze the whole screen without an error. This test finds such clashes before they run.
"""

import ast
from pathlib import Path

from textual import app
from textual import containers
from textual import screen
from textual import widgets
from textual.message_pump import MessagePump

import trading_agent.terminal

_MEANT_TO_SET = (
    'title',
    'collapsed',
    'display',
    'can_focus',
    'highlighted',
    'text',
    'placeholder',
    'value',
    'theme',
)


class _TextualNames:
    """The attribute names Textual's own classes use."""

    def names(self) -> set[str]:
        """Collects the names from sample objects and from the classes.

        Returns:
            set[str]: Every attribute name of the sampled Textual objects and their classes.
        """
        samples = [
            widgets.Static(''),
            widgets.Collapsible(),
            widgets.OptionList(),
            widgets.TextArea(),
            widgets.Input(),
            containers.VerticalScroll(),
            containers.Vertical(),
            screen.Screen(),
            screen.ModalScreen(),
            app.App(),
        ]
        names = set()
        for sample in samples:
            names.update(vars(sample).keys())
            for base in type(sample).__mro__:
                if base.__module__.startswith('textual') or base is MessagePump:
                    names.update(vars(base).keys())
        return names


class _AssignedNames:
    """The attribute names a module's classes set on self."""

    def by_class(self, path: Path) -> dict[str, set[str]]:
        """Reads one module.

        Args:
            path (Path): The module's file.

        Returns:
            dict[str, set[str]]: Each class's name and the names it assigns to self.
        """
        tree = ast.parse(path.read_text(encoding='utf-8'))
        found = {}
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            assigned = set()
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.Attribute)
                    and isinstance(item.value, ast.Name)
                    and item.value.id == 'self'
                    and isinstance(item.ctx, ast.Store)
                ):
                    assigned.add(item.attr)
            found[node.name] = assigned
        return found


class TestAttributeNames:
    """Tests for clashes with Textual's attribute names."""

    def test_no_class_overwrites_a_textual_attribute(self) -> None:
        """No class of the terminal package assigns to a name Textual uses, except the ones meant to be set."""
        textual_names = _TextualNames().names()
        root = Path(trading_agent.terminal.__file__).parent
        clashes = []
        for path in sorted(root.rglob('*.py')):
            for class_name, assigned in _AssignedNames().by_class(path).items():
                for name in sorted(assigned):
                    if name in textual_names and name not in _MEANT_TO_SET:
                        clashes.append(f'{path.name}: {class_name}.{name}')

        assert clashes == []
