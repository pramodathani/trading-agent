"""Runs every doctor check and prints a report.

`trading-agent preflight` runs the same checks plus the going-live ones: the trading mode, the desks' loss limits, the systemd service, and proof from the journals that orders have gone through UBI's dry run and that desks cannot share a stock.

Typical usage example:

  exit_code = Doctor(configuration, secrets).run()
  exit_code = Doctor(configuration, secrets, going_live=True).run()
"""

from trading_agent.channels import pairing_store
from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor_check
from trading_agent.doctor.checks import bubblewrap_check
from trading_agent.doctor.checks import chrome_check
from trading_agent.doctor.checks import claude_code_backend_check
from trading_agent.doctor.checks import desk_loss_limits_check
from trading_agent.doctor.checks import dry_run_order_check
from trading_agent.doctor.checks import gateway_token_check
from trading_agent.doctor.checks import injection_check
from trading_agent.doctor.checks import journal_search
from trading_agent.doctor.checks import market_calendar_check
from trading_agent.doctor.checks import mcp_servers_check
from trading_agent.doctor.checks import ollama_backend_check
from trading_agent.doctor.checks import openai_compatible_backend_check
from trading_agent.doctor.checks import ownership_conflict_check
from trading_agent.doctor.checks import python_version_check
from trading_agent.doctor.checks import searxng_check
from trading_agent.doctor.checks import service_check
from trading_agent.doctor.checks import telegram_check
from trading_agent.doctor.checks import telegram_pairing_check
from trading_agent.doctor.checks import trading_limits_check
from trading_agent.doctor.checks import trading_mode_check
from trading_agent.doctor.checks import unified_broker_interface_check
from trading_agent.workspace import workspace_layout

_STATUS_LABELS = {
    doctor_check.CheckStatus.OK: '[ ok ]',
    doctor_check.CheckStatus.WARNING: '[warn]',
    doctor_check.CheckStatus.FAILED: '[FAIL]',
}


class Doctor:
    """Checks that everything the agent depends on is in place."""

    def __init__(
        self,
        configuration: agent_configuration.AgentConfiguration,
        secrets: secrets_module.Secrets,
        going_live: bool = False,
    ):
        """Creates the doctor.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets read from the environment and .env.
            going_live (bool): Whether to add the going-live checks, for `trading-agent preflight`.
        """
        self._configuration = configuration
        self._secrets = secrets
        self._going_live = going_live

    def run(self) -> int:
        """Runs every check, prints one line per check, and a summary.

        Returns:
            int: 0 when nothing failed, 1 when at least one check failed, for use as the process exit code.
        """
        failed_count = 0
        warning_count = 0
        for check in self._checks():
            try:
                result = check.run()
            except Exception as error:  # noqa: BLE001
                result = doctor_check.CheckResult(
                    doctor_check.CheckStatus.FAILED,
                    f'The check itself crashed: {error!r}',
                )
            if result.status == doctor_check.CheckStatus.FAILED:
                failed_count += 1
            if result.status == doctor_check.CheckStatus.WARNING:
                warning_count += 1
            label = _STATUS_LABELS[result.status]
            print(f'{label} {check.name}: {result.message}')
        print(f'\n{failed_count} failed, {warning_count} warnings.')
        if self._going_live:
            print(self._verdict(failed_count))
        if failed_count:
            return 1
        return 0

    def _verdict(self, failed_count: int) -> str:
        """Says whether trading-agent is ready to trade live.

        Args:
            failed_count (int): How many checks failed.

        Returns:
            str: The verdict.
        """
        if failed_count:
            return 'Not ready to go live: fix the failed checks first.'
        if self._configuration.mode == 'live':
            return 'Running live.'
        return 'Ready to go live: set mode = "live" in trading_agent.toml and run systemctl --user restart trading-agent.'

    def _checks(self) -> list[doctor_check.DoctorCheck]:
        """Builds the list of checks, including one per configured backend.

        Returns:
            list[doctor_check.DoctorCheck]: The checks in the order they are reported.
        """
        checks = [
            python_version_check.PythonVersionCheck(),
            gateway_token_check.GatewayTokenCheck(self._secrets),
            unified_broker_interface_check.UnifiedBrokerInterfaceCheck(
                self._configuration.tradingmachine_environment_file,
            ),
        ]
        for backend_name, backend in self._configuration.backends.items():
            if backend.kind == 'ollama':
                checks.append(
                    ollama_backend_check.OllamaBackendCheck(
                        backend_name, backend
                    )
                )
            if backend.kind == 'openai_compatible':
                checks.append(
                    openai_compatible_backend_check.OpenAICompatibleBackendCheck(
                        backend_name,
                        backend,
                    )
                )
            if backend.kind == 'claude_code':
                checks.append(
                    claude_code_backend_check.ClaudeCodeBackendCheck(
                        backend_name,
                        self._secrets,
                    )
                )
        checks.append(
            searxng_check.SearxngCheck(self._configuration.web.searxng_base_url)
        )
        checks.append(
            telegram_check.TelegramCheck(
                self._configuration.telegram,
                self._secrets,
            )
        )
        checks.append(
            trading_limits_check.TradingLimitsCheck(
                workspace_layout.WorkspaceLayout(
                    self._configuration.workspace_directory
                ).trading_rules_file
            )
        )
        desk_names = []
        for desk in self._configuration.desks:
            desk_names.append(desk.name)
        checks.append(
            injection_check.InjectionCheck(
                workspace_layout.WorkspaceLayout(
                    self._configuration.workspace_directory
                ),
                desk_names,
            )
        )
        checks.append(
            market_calendar_check.MarketCalendarCheck(
                self._configuration.market_calendar_directory
            )
        )
        checks.append(
            mcp_servers_check.McpServersCheck(
                self._configuration.mcp_servers_file
            )
        )
        checks.append(bubblewrap_check.BubblewrapCheck())
        checks.append(chrome_check.ChromeCheck())
        if self._going_live:
            checks.extend(self._going_live_checks(desk_names))
        return checks

    def _going_live_checks(
        self, desk_names: list[str]
    ) -> list[doctor_check.DoctorCheck]:
        """The checks that only matter before trading live.

        Args:
            desk_names (list[str]): The desks.

        Returns:
            list[doctor_check.DoctorCheck]: The checks.
        """
        layout = workspace_layout.WorkspaceLayout(
            self._configuration.workspace_directory
        )
        search = journal_search.JournalSearch(layout, desk_names)
        return [
            service_check.ServiceCheck(),
            desk_loss_limits_check.DeskLossLimitsCheck(
                layout.trading_rules_file, desk_names
            ),
            dry_run_order_check.DryRunOrderCheck(search),
            ownership_conflict_check.OwnershipConflictCheck(search),
            telegram_pairing_check.TelegramPairingCheck(
                self._configuration.telegram.enabled,
                pairing_store.PairingStore(layout.telegram_pairing_file),
            ),
            trading_mode_check.TradingModeCheck(self._configuration.mode),
        ]
