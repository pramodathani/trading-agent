"""The `trading-agent skills` commands: list and import.

Typical usage example:

  exit_code = SkillCommands(layout, trader_names, passed_environment).run('import', '~/.hermes/skills/research', replace=False)
"""

import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from trading_agent.extensions import installed_packages
from trading_agent.skills import skill_importer
from trading_agent.skills import skill_library
from trading_agent.workspace import workspace_layout


class SkillCommands:
    """Lists and imports skills for the user."""

    def __init__(
        self,
        layout: workspace_layout.WorkspaceLayout,
        trader_names: Sequence[str],
        passed_environment: Mapping[str, str],
        output: TextIO = sys.stdout,
    ):
        """Creates the commands.

        Args:
            layout (workspace_layout.WorkspaceLayout): Where the skills are.
            trader_names (Sequence[str]): The traders whose own skills to list.
            passed_environment (Mapping[str, str]): The variables the bash sandbox receives, against which skills' needs are checked.
            output (TextIO): Where to print.
        """
        self._layout = layout
        self._trader_names = list(trader_names)
        self._passed_environment = passed_environment
        self._output = output

    def run(self, action: str, source: str | None, replace: bool) -> int:
        """Runs one action.

        Args:
            action (str): "list" or "import".
            source (str | None): For "import", the folder, zip file or git URL.
            replace (bool): For "import", whether to replace installed skills of the same name.

        Returns:
            int: 0 on success, 1 when the import failed or a skill in it was invalid.
        """
        if action == 'list':
            self._list()
            return 0
        return self._import(source, replace)

    def _list(self) -> None:
        """Prints each trader's usable and hidden skills."""
        for trader_name in self._trader_names:
            library = skill_library.SkillLibrary(
                self._layout.installed_skills_directory,
                self._layout.agent_skills_directory(trader_name),
                environment=self._passed_environment,
                package_skill_roots=installed_packages.InstalledPackages(
                    self._layout.packages_directory
                ).skill_roots,
            )
            self._print(f'Trader {trader_name}:')
            available = library.available()
            if not available:
                self._print('  no usable skills')
            for skill in available:
                self._print(
                    f'  {skill.origin:9}  {skill.name}: {skill.description}'
                )
            for hidden in library.hidden():
                self._print(
                    f'  hidden     {hidden.skill.name}: needs {", ".join(hidden.missing)}'
                )

    def _import(self, source: str | None, replace: bool) -> int:
        """Imports the skills in a source and prints what happened to each.

        Args:
            source (str | None): The folder, zip file or git URL.
            replace (bool): Whether to replace installed skills of the same name.

        Returns:
            int: 0 when every skill was imported or skipped, 1 otherwise.
        """
        importer = skill_importer.SkillImporter(
            self._layout.installed_skills_directory
        )
        try:
            results = importer.import_source(source, replace)
        except skill_importer.SkillImportError as error:
            self._print(str(error))
            return 1
        exit_code = 0
        for result in results:
            name = result.name or result.source.name
            line = f'{result.outcome:9}  {name}'
            if result.detail:
                line = f'{line}: {result.detail}'
            self._print(line)
            for warning in result.warnings:
                self._print(f'           warning: {warning}')
            if result.outcome == 'invalid':
                exit_code = 1
        if self._has_warnings(results):
            self._print(
                'Some skills contain text that looks like it tries to steer an AI. Read those passages before relying on the skill; remove its folder if you do not trust it.'
            )
        self._print(
            f'Installed skills live in {self._layout.installed_skills_directory}. Traders see them from their next turn.'
        )
        return exit_code

    def _has_warnings(
        self,
        results: list[skill_importer.ImportResult],
    ) -> bool:
        """Says whether any imported skill has a warning.

        Args:
            results (list[skill_importer.ImportResult]): The import results.

        Returns:
            bool: True when at least one result has a warning.
        """
        for result in results:
            if result.warnings:
                return True
        return False

    def _print(self, text: str) -> None:
        """Prints one line.

        Args:
            text (str): The line.
        """
        print(text, file=self._output)
