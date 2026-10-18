"""The Schedule page: a desk's scheduled jobs with their next runs, the latest runs, its price alerts, and a form for a new job.

It copies the web page's CronPage.tsx.

Typical usage example:

  app.push_screen(ScheduleScreen('general'))
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import screen
from textual import widgets
from textual import work
from textual.content import Content

from trading_agent.terminal import formatter
from trading_agent.terminal import gateway_client
from trading_agent.terminal.screens import page_screen


class ScheduleScreen(page_screen.PageScreen):
    """The Schedule page."""

    TITLE_TEXT = 'Schedule'
    REFRESH_SECONDS = 30.0
    PER_DESK = True

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('d', 'next_desk', 'Next desk'),
        binding.Binding('n', 'new_job', 'New job'),
        binding.Binding('g', 'run_job', 'Run job now'),
        binding.Binding('delete', 'delete_selected', 'Delete job or alert'),
    ]

    def __init__(self, desk_name: str):
        """Creates the page.

        Args:
            desk_name (str): The desk the chat shows.
        """
        super().__init__(desk_name)
        self._formatter = formatter.Formatter()

    def compose_page(self):
        """Builds the jobs, runs and alerts tables.

        Yields:
            Widget: The sections, in a scroll area.
        """
        with containers.VerticalScroll(classes='page-body'):
            yield widgets.Static(
                '[b]Jobs[/b] [dim]n new · g run now · delete removes[/dim]',
                classes='page-heading',
            )
            yield widgets.DataTable(id='schedule-jobs', cursor_type='row')
            yield widgets.Static('[b]Latest runs[/b]', classes='page-heading')
            yield widgets.DataTable(id='schedule-runs', cursor_type='row')
            yield widgets.Static(
                '[b]Price alerts[/b] [dim]delete removes[/dim]',
                classes='page-heading',
            )
            yield widgets.DataTable(id='schedule-alerts', cursor_type='row')

    def on_mount(self) -> None:
        """Sets up the tables, then reads the schedule."""
        self.table('schedule-jobs').add_columns(
            'Job', 'Schedule', 'Next runs', 'Last run', 'By'
        )
        self.table('schedule-runs').add_columns(
            'At', 'Job', 'Outcome', 'Detail'
        )
        self.table('schedule-alerts').add_columns(
            'Symbol', 'Condition', 'Price', 'Note', 'Set'
        )
        super().on_mount()

    @work(exclusive=True, group='page')
    async def refresh_page(self) -> None:
        """Reads the desk's jobs, runs and alerts."""
        gateway = self.app.gateway
        try:
            jobs = await gateway.jobs(self.desk_name)
            alerts = await gateway.alerts(self.desk_name)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        table = self.table('schedule-jobs')
        table.clear()
        for job in jobs.get('jobs') or []:
            next_runs = []
            for moment in (job.get('next_runs') or [])[:2]:
                next_runs.append(self._formatter.day_time(str(moment)))
            table.add_row(
                str(job.get('name', '')),
                str(
                    job.get('description')
                    or job.get('schedule')
                    or job.get('run_at')
                    or ''
                ),
                ', '.join(next_runs) or '—',
                self._formatter.day_time(str(job.get('last_run')))
                if job.get('last_run')
                else '—',
                str(job.get('created_by', '')),
                key=str(job.get('job_id', '')),
            )
        runs = self.table('schedule-runs')
        runs.clear()
        for run in jobs.get('recent_runs') or []:
            runs.add_row(
                self._formatter.day_time(str(run.get('at', ''))),
                str(run.get('name', '')),
                str(run.get('outcome', '')),
                str(run.get('detail', ''))[:80],
            )
        alert_table = self.table('schedule-alerts')
        alert_table.clear()
        for alert in alerts.get('alerts') or []:
            alert_table.add_row(
                str(alert.get('symbol', '')),
                str(alert.get('condition', '')),
                self._formatter.price_text(alert.get('price')),
                str(alert.get('note', '')),
                self._formatter.day_time(str(alert.get('created_at', ''))),
                key=str(alert.get('alert_id', '')),
            )

    def action_new_job(self) -> None:
        """Opens the form for a new job."""

        def create(job: dict[str, Any] | None) -> None:
            """Creates the job once the form is filled in.

            Args:
                job (dict[str, Any] | None): The job, or None when cancelled.
            """
            if job is not None:
                self._create(job)

        self.app.push_screen(NewJobForm(self.desk_name), create)

    def action_run_job(self) -> None:
        """Runs the highlighted job now."""
        job_id = self.selected_key('schedule-jobs')
        if job_id is not None:
            self._run(job_id)

    def action_delete_selected(self) -> None:
        """Deletes the highlighted job or alert, whichever table has the focus."""
        focused = self.focused
        if focused is self.table('schedule-alerts'):
            alert_id = self.selected_key('schedule-alerts')
            if alert_id is not None:
                self._delete_alert(alert_id)
            return
        job_id = self.selected_key('schedule-jobs')
        if job_id is not None:
            self._delete_job(job_id)

    @work(group='action')
    async def _create(self, job: dict[str, Any]) -> None:
        """Creates a job.

        Args:
            job (dict[str, Any]): The job.
        """
        try:
            await self.app.gateway.create_job(self.desk_name, job)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify(f'Scheduled {job["name"]}.', timeout=3)
        self.refresh_page()

    @work(group='action')
    async def _run(self, job_id: str) -> None:
        """Runs a job now.

        Args:
            job_id (str): The job.
        """
        try:
            await self.app.gateway.run_job(self.desk_name, job_id)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify('The job started.', timeout=3)
        self.refresh_page()

    @work(group='action')
    async def _delete_job(self, job_id: str) -> None:
        """Deletes a job.

        Args:
            job_id (str): The job.
        """
        try:
            await self.app.gateway.delete_job(self.desk_name, job_id)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify('Job removed.', timeout=3)
        self.refresh_page()

    @work(group='action')
    async def _delete_alert(self, alert_id: str) -> None:
        """Deletes a price alert.

        Args:
            alert_id (str): The alert.
        """
        try:
            await self.app.gateway.delete_alert(self.desk_name, alert_id)
        except gateway_client.GatewayError as error:
            self.problem(error.message)
            return
        self.notify('Alert removed.', timeout=3)
        self.refresh_page()


class NewJobForm(screen.ModalScreen[dict[str, Any] | None]):
    """The form for a new scheduled job, with the web page's fields."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape', 'cancel', 'Cancel'),
        binding.Binding('ctrl+s', 'submit', 'Schedule'),
    ]

    def __init__(self, desk_name: str):
        """Creates the form.

        Args:
            desk_name (str): The desk the job is for.
        """
        super().__init__(classes='picker-screen')
        self._desk_name = desk_name

    def compose(self):
        """Builds the form.

        Yields:
            Widget: The fields, switches, error line and hint.
        """
        with containers.VerticalScroll(classes='picker'):
            yield widgets.Static(
                Content.from_markup(
                    '[b]New job for $desk[/b]', desk=self._desk_name
                ),
                classes='picker-title',
            )
            yield widgets.Input(
                placeholder='Name, such as Morning check', id='job-name'
            )
            yield widgets.Input(
                placeholder='Schedule: five cron fields in India time, such as 5 9 * * 1-5',
                id='job-schedule',
            )
            yield widgets.RadioSet(
                widgets.RadioButton(
                    'Wake the desk with instructions',
                    value=True,
                    id='job-kind-agent',
                ),
                widgets.RadioButton(
                    'Run a command, no model', id='job-kind-command'
                ),
                id='job-kind',
            )
            yield widgets.TextArea(
                '',
                id='job-text',
                compact=True,
                placeholder='Instructions for the desk, or the shell command to run',
            )
            yield widgets.Checkbox(
                'Trading days only', value=True, id='job-trading-days'
            )
            yield widgets.Checkbox(
                'Only while NSE equities trade', id='job-market-hours'
            )
            yield widgets.Static('', id='job-error')
            yield widgets.Static(
                '[dim]tab moves between fields · ctrl+s schedules · esc cancels[/dim]',
                classes='picker-hint',
            )

    def on_mount(self) -> None:
        """Puts the cursor in the name box."""
        self.query_one('#job-name', widgets.Input).focus()

    def action_submit(self) -> None:
        """Checks the fields and returns the job."""
        name = self.query_one('#job-name', widgets.Input).value.strip()
        schedule = self.query_one('#job-schedule', widgets.Input).value.strip()
        text = self.query_one('#job-text', widgets.TextArea).text.strip()
        if not name or not schedule or not text:
            self.query_one('#job-error', widgets.Static).update(
                Content.from_markup(
                    '[$error]Fill in the name, the schedule, and the instructions or command.[/]'
                )
            )
            return
        as_command = self.query_one(
            '#job-kind-command', widgets.RadioButton
        ).value
        instructions = text
        command = None
        if as_command:
            instructions = None
            command = text
        self.dismiss(
            {
                'name': name,
                'schedule': schedule,
                'run_at': None,
                'instructions': instructions,
                'command': command,
                'trading_days_only': self.query_one(
                    '#job-trading-days', widgets.Checkbox
                ).value,
                'market_hours_only': self.query_one(
                    '#job-market-hours', widgets.Checkbox
                ).value,
            }
        )

    def action_cancel(self) -> None:
        """Closes the form without a job."""
        self.dismiss(None)
