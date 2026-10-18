"""The Models page: each desk's model order and preference, today's usage by desk and model, and Claude's subscription limits.

It copies the web page's ModelsPage.tsx.

Typical usage example:

  app.push_screen(ModelsScreen('general'))
"""

from textual import containers
from textual import widgets
from textual import work

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen


class ModelsScreen(page_screen.PageScreen):
    """The Models page."""

    TITLE_TEXT = 'Models'
    REFRESH_SECONDS = 20.0

    def compose_page(self):
        """Builds the three tables.

        Yields:
            Widget: The sections, in a scroll area.
        """
        with containers.VerticalScroll(classes='page-body'):
            yield widgets.Static(
                "[b]Model order[/b] [dim]choose a desk's model in the chat with alt+p[/dim]",
                classes='page-heading',
            )
            yield widgets.DataTable(id='models-order', cursor_type='row')
            yield widgets.Static('[b]Usage today[/b]', classes='page-heading')
            yield widgets.DataTable(id='models-usage', cursor_type='row')
            yield widgets.Static(
                '[b]Subscription limits[/b]', classes='page-heading'
            )
            yield widgets.DataTable(id='models-limits', cursor_type='row')

    def on_mount(self) -> None:
        """Sets up the tables, then reads the usage."""
        self.table('models-order').add_columns('Desk', 'Order', 'Preferred')
        self.table('models-usage').add_columns(
            'Desk',
            'Model',
            'Calls',
            'Prompt',
            'Cached',
            'Answer',
            'Claude at API prices',
            'Charged',
        )
        self.table('models-limits').add_columns(
            'Backend', 'Limit', 'Status', 'Resets'
        )
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the desks and the usage."""
        gateway = self.app.gateway
        try:
            desks = await gateway.desks()
            usage = await gateway.usage()
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        numbers = formatter.Formatter()
        order = self.table('models-order')
        order.clear()
        for desk in desks.get('desks') or []:
            order.add_row(
                str(desk.get('name', '')),
                '; '.join(str(line) for line in desk.get('models') or []),
                str(desk.get('preferred_model') or 'configured order'),
            )
        table = self.table('models-usage')
        table.clear()
        for desk_name, backends in (usage.get('desks') or {}).items():
            for backend_name, counts in (backends or {}).items():
                table.add_row(
                    desk_name,
                    backend_name,
                    numbers.number(counts.get('calls')),
                    numbers.token_count(
                        float(counts.get('prompt_tokens') or 0)
                    ),
                    numbers.token_count(
                        float(counts.get('cache_read_tokens') or 0)
                    ),
                    numbers.token_count(
                        float(counts.get('completion_tokens') or 0)
                    ),
                    f'${float(counts.get("api_equivalent_cost_usd") or 0):.2f}',
                    f'${float(counts.get("cost_usd") or 0):.2f}',
                )
        limits = self.table('models-limits')
        limits.clear()
        for backend_name, limit in (usage.get('rate_limits') or {}).items():
            resets = '—'
            if limit.get('resets_at'):
                resets = numbers.day_time(str(limit['resets_at']))
            limits.add_row(
                backend_name,
                str(limit.get('limit', '')),
                str(limit.get('status', '')),
                resets,
            )
