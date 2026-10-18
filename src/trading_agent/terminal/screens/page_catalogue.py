"""The list of the terminal program's pages, for the slash commands, the F2 page list and the command palette.

Typical usage example:

  for page in PageCatalogue().pages():
      print(page.command, page.title)
"""

import dataclasses

from trading_agent.terminal.screens import activity_screen
from trading_agent.terminal.screens import apps_screen
from trading_agent.terminal.screens import channels_screen
from trading_agent.terminal.screens import checkpoints_screen
from trading_agent.terminal.screens import desks_screen
from trading_agent.terminal.screens import extensions_screen
from trading_agent.terminal.screens import files_screen
from trading_agent.terminal.screens import models_screen
from trading_agent.terminal.screens import page_screen
from trading_agent.terminal.screens import schedule_screen
from trading_agent.terminal.screens import sessions_screen
from trading_agent.terminal.screens import settings_screen
from trading_agent.terminal.screens import skills_screen
from trading_agent.terminal.screens import trading_screen


@dataclasses.dataclass(frozen=True)
class Page:
    """One page.

    Attributes:
        command: The slash command that opens it, such as "/trading".
        title: Its title.
        description: What it shows.
        screen_class: The screen class that draws it.
    """

    command: str
    title: str
    description: str
    screen_class: type[page_screen.PageScreen]


class PageCatalogue:
    """The pages, in the web page's sidebar order."""

    def pages(self) -> list[Page]:
        """Every page.

        Returns:
            list[Page]: The pages.
        """
        return [
            Page(
                '/desks',
                'Desks',
                'every desk, with pause, resume, flatten and chat',
                desks_screen.DesksScreen,
            ),
            Page(
                '/activity',
                'Activity',
                "today's events from every desk, live",
                activity_screen.ActivityScreen,
            ),
            Page(
                '/trading',
                'Trading',
                "positions, open orders, UBI's order book and the kill switch",
                trading_screen.TradingScreen,
            ),
            Page(
                '/sessions',
                'Sessions',
                "a desk's sessions, memory search, summaries and notes",
                sessions_screen.SessionsScreen,
            ),
            Page(
                '/files',
                'Files',
                "edit your files and review the desks' proposals",
                files_screen.FilesScreen,
            ),
            Page(
                '/checkpoints',
                'Checkpoints',
                "snapshots of a desk's own files, with restore",
                checkpoints_screen.CheckpointsScreen,
            ),
            Page(
                '/schedule',
                'Schedule',
                "a desk's scheduled jobs and price alerts",
                schedule_screen.ScheduleScreen,
            ),
            Page(
                '/skills',
                'Skills',
                "a desk's usable and hidden skills",
                skills_screen.SkillsScreen,
            ),
            Page(
                '/extensions',
                'Extensions',
                'subagents, MCP servers and packages',
                extensions_screen.ExtensionsScreen,
            ),
            Page(
                '/models',
                'Models',
                "model order, today's usage and Claude's limits",
                models_screen.ModelsScreen,
            ),
            Page(
                '/channels',
                'Channels',
                'Telegram state and pairings',
                channels_screen.ChannelsScreen,
            ),
            Page(
                '/settings',
                'Settings',
                'standing permissions and the configuration',
                settings_screen.SettingsScreen,
            ),
            Page(
                '/apps',
                'Apps',
                "the packages' web apps",
                apps_screen.AppsScreen,
            ),
        ]

    def find(self, command: str) -> Page | None:
        """The page a slash command opens.

        Args:
            command (str): Such as "/trading".

        Returns:
            Page | None: The page, or None when the command opens none.
        """
        for page in self.pages():
            if page.command == command:
                return page
        return None
