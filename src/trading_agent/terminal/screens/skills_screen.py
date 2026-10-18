"""The Skills page: the skills a desk can follow, with their use counts, and the skills hidden from it with what each is missing.

It copies the web page's SkillsPage.tsx.

Typical usage example:

  app.push_screen(SkillsScreen('general'))
"""

from typing import ClassVar

from textual import binding
from textual import containers
from textual import widgets
from textual import work

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen


class SkillsScreen(page_screen.PageScreen):
    """The Skills page."""

    TITLE_TEXT = 'Skills'
    REFRESH_SECONDS = 30.0
    PER_DESK = True

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('d', 'next_desk', 'Next desk'),
    ]

    def compose_page(self):
        """Builds the two tables.

        Yields:
            Widget: The sections, in a scroll area.
        """
        with containers.VerticalScroll(classes='page-body'):
            yield widgets.Static('[b]Usable[/b]', classes='page-heading')
            yield widgets.DataTable(id='skills-available', cursor_type='row')
            yield widgets.Static(
                '[b]Hidden[/b] [dim]a skill is hidden while something it needs is missing[/dim]',
                classes='page-heading',
            )
            yield widgets.DataTable(id='skills-hidden', cursor_type='row')

    def on_mount(self) -> None:
        """Sets up the tables, then reads the skills."""
        self.table('skills-available').add_columns(
            'Skill',
            'What it is for',
            'Origin',
            'Uses',
            'With trouble',
            'Last used',
        )
        self.table('skills-hidden').add_columns('Skill', 'Missing')
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the desk's skills."""
        try:
            answer = await self.app.gateway.skills(self.desk_name)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        clock = formatter.Formatter()
        table = self.table('skills-available')
        table.clear()
        for skill in answer.get('available') or []:
            origin = 'yours'
            if skill.get('origin') == 'agent':
                origin = 'written by the desk'
            last_used = '—'
            if skill.get('last_used'):
                last_used = clock.day_time(str(skill['last_used']))
            table.add_row(
                str(skill.get('name', '')),
                str(skill.get('description', ''))[:70],
                origin,
                str(skill.get('uses', 0)),
                str(skill.get('troubled_uses', 0)),
                last_used,
            )
        hidden = self.table('skills-hidden')
        hidden.clear()
        for skill in answer.get('hidden') or []:
            missing = skill.get('missing') or []
            hidden.add_row(
                str(skill.get('name', '')),
                ', '.join(str(item) for item in missing),
            )
