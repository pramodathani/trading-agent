"""Scans the files that become the traders' instructions for text that tries to steer an AI.

It reads the shared instruction files, each trader's Persona.md and Memory.md, and every installed skill's SKILL.md. Memory.md is included because a trader writes it itself, sometimes after reading web pages.

Typical usage example:

  result = InjectionCheck(layout, ['main']).run()
"""

from collections.abc import Sequence
from pathlib import Path

from trading_agent.doctor import doctor_check
from trading_agent.extensions import injection_scanner
from trading_agent.workspace import workspace_layout


class InjectionCheck(doctor_check.DoctorCheck):
    """Checks the instruction files and installed skills for prompt injection."""

    name = 'Prompt-injection scan of instructions and skills'

    def __init__(
        self,
        layout: workspace_layout.WorkspaceLayout,
        trader_names: Sequence[str],
    ):
        """Creates the check.

        Args:
            layout (workspace_layout.WorkspaceLayout): Where the files are.
            trader_names (Sequence[str]): The traders whose files to scan.
        """
        self._layout = layout
        self._trader_names = list(trader_names)

    def run(self) -> doctor_check.CheckResult:
        """Scans every file.

        Returns:
            doctor_check.CheckResult: OK with the number of files scanned, or a warning listing each suspicious passage.
        """
        scanner = injection_scanner.InjectionScanner()
        paths = self._paths()
        problems = []
        for path in paths:
            text = path.read_text(encoding='utf-8', errors='replace')
            for finding in scanner.scan(text):
                problems.append(
                    f'{path}, line {finding.line_number}: {finding.rule} ("{finding.excerpt}")'
                )
        if problems:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                'Read these passages; they look like they try to steer an AI: '
                + '; '.join(problems),
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'Nothing suspicious in {len(paths)} files.',
        )

    def _paths(self) -> list[Path]:
        """The files to scan that exist.

        Returns:
            list[Path]: The files.
        """
        candidates = [
            self._layout.agents_file,
            self._layout.user_file,
            self._layout.trading_rules_file,
        ]
        for trader_name in self._trader_names:
            candidates.append(self._layout.persona_file(trader_name))
            candidates.append(self._layout.memory_file(trader_name))
        installed = self._layout.installed_skills_directory
        if installed.is_dir():
            candidates.extend(sorted(installed.glob('*/SKILL.md')))
        paths = []
        for path in candidates:
            if path.is_file():
                paths.append(path)
        return paths
