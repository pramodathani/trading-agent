"""Runs every doctor check and prints a report.

Typical usage example:

  exit_code = Doctor(configuration, secrets).run()
"""

from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor_check
from trading_agent.doctor.checks import bubblewrap_check
from trading_agent.doctor.checks import chrome_check
from trading_agent.doctor.checks import claude_code_backend_check
from trading_agent.doctor.checks import gateway_token_check
from trading_agent.doctor.checks import injection_check
from trading_agent.doctor.checks import market_calendar_check
from trading_agent.doctor.checks import mcp_servers_check
from trading_agent.doctor.checks import ollama_backend_check
from trading_agent.doctor.checks import openai_compatible_backend_check
from trading_agent.doctor.checks import python_version_check
from trading_agent.doctor.checks import searxng_check
from trading_agent.doctor.checks import telegram_check
from trading_agent.doctor.checks import trading_limits_check
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
    ):
        """Creates the doctor.

        Args:
            configuration (agent_configuration.AgentConfiguration): The agent's configuration.
            secrets (secrets_module.Secrets): The secrets read from the environment and .env.
        """
        self._configuration = configuration
        self._secrets = secrets

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
        if failed_count:
            return 1
        return 0

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
        return checks
