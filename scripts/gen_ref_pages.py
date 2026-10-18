"""Builds the API reference pages from the source tree, at documentation build time.

There is one page per module, and every page is generated, so a module added anywhere under src/trading_agent appears in the reference without anyone listing it. The module is the page's title, and each public class is a section in the order the module defines it, with its methods beneath it, so the page's table of contents lists every class with its members. The landing page of the section is a tree of every class by inheritance, as in tradingmachine's reference.

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
_HIERARCHY_PAGE_NAME = 'index.md'


class ModuleSource:
    """What the reference needs to know about one module, read from its source without importing it.

    Attributes:
        dotted_path: The module's import path, such as trading_agent.risk.risk_engine.
        class_names: The module's public top-level classes, in the order the module defines them.
        constant_names: The module's public top-level constants, in the order the module defines them.
        base_expressions: Each public class's bases, as the source text names them, such as tool.Tool.
        import_aliases: Each name the module binds by importing, mapped to the dotted path it stands for.
    """

    def __init__(self, path: Path, dotted_path: str):
        """Reads the module's public classes, their bases, its constants and its imports.

        Args:
            path (Path): The module's source file.
            dotted_path (str): Its import path.

        Raises:
            SyntaxError: The module's source cannot be parsed.
        """
        self.dotted_path = dotted_path
        self.class_names: list[str] = []
        self.constant_names: list[str] = []
        self.base_expressions: dict[str, list[str]] = {}
        self.import_aliases: dict[str, str] = {}
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith('_'):
                self._read_class(node)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self._read_constant(target)
            if isinstance(node, ast.ImportFrom):
                self._read_import_from(node)
            if isinstance(node, ast.Import):
                self._read_import(node)

    def _read_class(self, node: ast.ClassDef) -> None:
        """Records one public class and the source text of its bases.

        Args:
            node (ast.ClassDef): The class.
        """
        self.class_names.append(node.name)
        bases = []
        for base in node.bases:
            bases.append(ast.unparse(base))
        self.base_expressions[node.name] = bases

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

    def _read_import_from(self, node: ast.ImportFrom) -> None:
        """Records the names a from-import binds, such as tool for from trading_agent.tools import tool.

        Args:
            node (ast.ImportFrom): The import statement.
        """
        if node.module is None:
            return
        for alias in node.names:
            bound_name = alias.asname or alias.name
            self.import_aliases[bound_name] = f'{node.module}.{alias.name}'

    def _read_import(self, node: ast.Import) -> None:
        """Records the names a plain import binds.

        Args:
            node (ast.Import): The import statement.
        """
        for alias in node.names:
            bound_name = alias.asname or alias.name
            self.import_aliases[bound_name] = alias.name

    def resolve_base(self, expression: str) -> str:
        """Turns the source text of a base class into its full dotted path.

        Args:
            expression (str): The base as the source names it, such as tool.Tool or Exception.

        Returns:
            str: The base's dotted path, such as trading_agent.tools.tool.Tool, or the expression unchanged when it names nothing this module defines or imports.
        """
        if expression in self.class_names:
            return f'{self.dotted_path}.{expression}'
        first_name, separator, rest = expression.partition('.')
        if separator and first_name in self.import_aliases:
            return f'{self.import_aliases[first_name]}.{rest}'
        if expression in self.import_aliases:
            return self.import_aliases[expression]
        return expression

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


class ClassHierarchyPage:
    """The reference section's landing page, a tree of every public class by inheritance.

    Attributes:
        bases: Each class's dotted path, mapped to the dotted paths of its bases.
        module_of_class: Each class's dotted path, mapped to the dotted path of its module.
    """

    def __init__(self):
        """Starts with no classes recorded."""
        self.bases: dict[str, list[str]] = {}
        self.module_of_class: dict[str, str] = {}

    def add_module(self, module: ModuleSource) -> None:
        """Records every public class of one module with its resolved bases.

        Args:
            module (ModuleSource): The module.
        """
        for class_name in module.class_names:
            class_path = f'{module.dotted_path}.{class_name}'
            resolved_bases = []
            for expression in module.base_expressions[class_name]:
                resolved_bases.append(module.resolve_base(expression))
            self.bases[class_path] = resolved_bases
            self.module_of_class[class_path] = module.dotted_path

    def _project_bases(self, class_path: str) -> list[str]:
        """Lists the bases of a class that are themselves classes of trading-agent.

        Args:
            class_path (str): The class's dotted path.

        Returns:
            list[str]: The bases' dotted paths, in the order the class names them.
        """
        project_bases = []
        for base in self.bases[class_path]:
            if base in self.bases:
                project_bases.append(base)
        return project_bases

    def _parent(self, class_path: str) -> str | None:
        """Chooses where a class hangs in the tree.

        A class with exactly one base in trading-agent hangs under it. A class with none, or with several side by side, is a root of the tree, and its bases are named beside it instead.

        Args:
            class_path (str): The class's dotted path.

        Returns:
            str | None: The parent class's dotted path, or None for a root.
        """
        project_bases = self._project_bases(class_path)
        if len(project_bases) == 1:
            return project_bases[0]
        return None

    def _line_for(self, class_path: str, depth: int) -> str:
        """Writes one class as a line of the nested list.

        Args:
            class_path (str): The class's dotted path.
            depth (int): How deep it is nested, zero for a root.

        Returns:
            str: The Markdown line, ending in a newline.
        """
        short_name = class_path.rsplit('.', 1)[1]
        module_path = self.module_of_class[class_path]
        indent = '    ' * depth
        line = f'{indent}- [`{short_name}`][{class_path}] in `{module_path}`'
        project_bases = self._project_bases(class_path)
        external_bases = []
        for base in self.bases[class_path]:
            if base not in self.bases and base != 'object':
                external_bases.append(base)
        if len(project_bases) > 1:
            base_names = []
            for base in project_bases:
                base_names.append(f'`{base.rsplit(".", 1)[1]}`')
            line += f', inheriting {", ".join(base_names)}'
        elif not project_bases and external_bases:
            base_names = []
            for base in external_bases:
                base_names.append(f'`{base}`')
            line += f', from {", ".join(base_names)}'
        return line + '\n'

    def _write_branch(
        self,
        class_path: str,
        depth: int,
        children: dict[str, list[str]],
        lines: list[str],
    ) -> None:
        """Writes a class and, beneath it, every class that hangs under it.

        Args:
            class_path (str): The class's dotted path.
            depth (int): How deep it is nested.
            children (dict[str, list[str]]): Each class's dotted path, mapped to the classes that hang under it.
            lines (list[str]): The Markdown lines the branch is appended to.
        """
        lines.append(self._line_for(class_path, depth))
        for child in children.get(class_path, []):
            self._write_branch(child, depth + 1, children, lines)

    def markdown(self) -> str:
        """Writes the whole page.

        Returns:
            str: The Markdown of the page.
        """
        children: dict[str, list[str]] = {}
        roots = []
        for class_path in self.bases:
            parent = self._parent(class_path)
            if parent is None:
                roots.append(class_path)
            else:
                children.setdefault(parent, []).append(class_path)
        lines = [
            '# Class hierarchy\n',
            '\n',
            'This section documents every public class of trading-agent, one page per module. The menu on the left follows the folders of `src/trading_agent`. On each page the module comes first, then each class in the order the module defines it, with its methods beneath it, and the menu on the right lists them.\n',
            '\n',
            f'The tree below shows all {len(self.bases)} classes by inheritance. A class hangs under its base when it has exactly one base in trading-agent. A class whose bases all come from outside trading-agent, or that inherits several of its classes side by side, starts a new branch, and those bases are named beside it.\n',
            '\n',
        ]
        for root in roots:
            self._write_branch(root, 0, children, lines)
        return ''.join(lines)


class ReferencePageBuilder:
    """Writes one reference page per module of the trading_agent package.

    Attributes:
        root: The project folder, the parent of this file's folder.
        source_root: The folder the package is imported from.
        navigation: The reference section's navigation, collected while the pages are written.
        hierarchy: The class hierarchy page every module's classes are recorded in.
    """

    def __init__(self, root: Path | None = None):
        """Prepares the builder.

        Args:
            root (Path | None): The project folder, or None for the parent of this file's folder.
        """
        self.root = root or Path(__file__).resolve().parent.parent
        self.source_root = self.root / _SOURCE_DIRECTORY
        self.navigation = mkdocs_gen_files.Nav()
        self.hierarchy = ClassHierarchyPage()

    def build(self) -> None:
        """Writes every module's page, the class hierarchy and the section's navigation file.

        Raises:
            SyntaxError: A module's source cannot be parsed.
        """
        for path in sorted((self.source_root / _PACKAGE).rglob('*.py')):
            self._build_page(path)
        with mkdocs_gen_files.open(
            Path('reference') / _HIERARCHY_PAGE_NAME, 'w'
        ) as page:
            page.write(self.hierarchy.markdown())
        with mkdocs_gen_files.open('reference/SUMMARY.md', 'w') as summary:
            summary.write(f'* [Class hierarchy]({_HIERARCHY_PAGE_NAME})\n')
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
        self.hierarchy.add_module(module)
        self.navigation[parts] = page_path.as_posix()
        full_page_path = Path('reference') / page_path
        with mkdocs_gen_files.open(full_page_path, 'w') as page:
            page.write(module.markdown())
        mkdocs_gen_files.set_edit_path(
            full_page_path, path.relative_to(self.root)
        )


ReferencePageBuilder().build()
