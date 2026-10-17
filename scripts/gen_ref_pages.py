"""Builds the API reference pages from the source tree, at documentation build time.

There is one page per module, and every page is generated, so a module added anywhere under src/trading_agent appears in the reference without anyone listing it. The module is the page's title, and each public class is a section in the order the module defines it, with its methods beneath it, so the page's table of contents lists every class with its members.

Nothing is written into the project: mkdocs_gen_files holds the pages in memory for the length of the build, and the section's navigation is written to reference/SUMMARY.md for the literate-nav plugin to read.

Typical usage example:

  plugins:
    - gen-files:
        scripts:
          - scripts/gen_ref_pages.py
"""

import ast
from pathlib import Path

import mkdocs_gen_files

_SOURCE_DIRECTORY = 'src'
_PACKAGE = 'trading_agent'
_EXCLUDED_PARTS = ('__pycache__',)


class ModuleSource:
    """What the reference needs to know about one module, read from its source without importing it.

    Attributes:
        dotted_path: The module's import path, such as trading_agent.risk.risk_engine.
        class_names: The module's public top-level classes, in the order the module defines them.
        constant_names: The module's public top-level constants, in the order the module defines them.
    """

    def __init__(self, path: Path, dotted_path: str):
        """Reads the module's public classes and constants.

        Args:
            path (Path): The module's source file.
            dotted_path (str): Its import path.

        Raises:
            SyntaxError: The module's source cannot be parsed.
        """
        self.dotted_path = dotted_path
        self.class_names: list[str] = []
        self.constant_names: list[str] = []
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith('_'):
                self.class_names.append(node.name)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self._read_constant(target)

    def _read_constant(self, target: ast.expr) -> None:
        """Records one assignment when it binds a public constant.

        Args:
            target (ast.expr): What the value is assigned to.
        """
        if not isinstance(target, ast.Name):
            return
        if target.id.startswith('_') or not target.id.isupper():
            return
        self.constant_names.append(target.id)

    def markdown(self) -> str:
        """Writes the module's page.

        Returns:
            str: The Markdown, one mkdocstrings block for the module and one per class.
        """
        lines = [
            f'::: {self.dotted_path}',
            '    options:',
            '      heading_level: 1',
            '      show_root_full_path: true',
        ]
        if self.constant_names:
            lines.append('      members:')
            for name in self.constant_names:
                lines.append(f'        - {name}')
        else:
            lines.append('      members: false')
        lines.append('')
        for class_name in self.class_names:
            lines.append(f'::: {self.dotted_path}.{class_name}')
            lines.append('    options:')
            lines.append('      heading_level: 2')
            lines.append('')
        return '\n'.join(lines) + '\n'


class ReferencePageBuilder:
    """Writes one reference page per module of the trading_agent package.

    Attributes:
        root: The project folder, the parent of this file's folder.
        source_root: The folder the package is imported from.
        navigation: The reference section's navigation, collected while the pages are written.
    """

    def __init__(self, root: Path | None = None):
        """Prepares the builder.

        Args:
            root (Path | None): The project folder, or None for the parent of this file's folder.
        """
        self.root = root or Path(__file__).resolve().parent.parent
        self.source_root = self.root / _SOURCE_DIRECTORY
        self.navigation = mkdocs_gen_files.Nav()

    def build(self) -> None:
        """Writes every module's page and the section's navigation file.

        Raises:
            SyntaxError: A module's source cannot be parsed.
        """
        for path in sorted((self.source_root / _PACKAGE).rglob('*.py')):
            self._build_page(path)
        with mkdocs_gen_files.open('reference/SUMMARY.md', 'w') as summary:
            summary.writelines(self.navigation.build_literate_nav())

    def _build_page(self, path: Path) -> None:
        """Writes one module's page, unless the module is excluded or empty.

        A package's __init__.py becomes the package's index.md; an empty one is skipped, and so is __main__.py, which only starts the application.

        Args:
            path (Path): The module's source file.

        Raises:
            SyntaxError: The module's source cannot be parsed.
        """
        module_path = path.relative_to(self.source_root).with_suffix('')
        for part in module_path.parts:
            if part in _EXCLUDED_PARTS:
                return
        parts = tuple(module_path.parts)
        page_path = module_path.with_suffix('.md')
        if parts[-1] == '__init__':
            if not path.read_text(encoding='utf-8').strip():
                return
            parts = parts[:-1]
            page_path = page_path.with_name('index.md')
        elif parts[-1].startswith('__'):
            return
        module = ModuleSource(path, '.'.join(parts))
        self.navigation[parts] = page_path.as_posix()
        full_page_path = Path('reference') / page_path
        with mkdocs_gen_files.open(full_page_path, 'w') as page:
            page.write(module.markdown())
        mkdocs_gen_files.set_edit_path(
            full_page_path, path.relative_to(self.root)
        )


ReferencePageBuilder().build()
