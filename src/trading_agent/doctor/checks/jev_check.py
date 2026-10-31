"""Checks that the Jev decision model is reachable with the TypeSafe API key, when a trader uses Jev.

The key is never shown. With the key set, the check asks Jev one question about a tiny made-up state, which costs a few hundred input tokens.

Typical usage example:

  result = JevCheck(jev_configuration, secrets, workspace_layout, trader_names).run()
"""

import asyncio
import tomllib
from collections.abc import Sequence

from trading_agent.configuration import agent_configuration
from trading_agent.configuration import secrets as secrets_module
from trading_agent.doctor import doctor_check
from trading_agent.trading import jev_client
from trading_agent.workspace import workspace_layout as workspace_layout_module

_VARIABLE = 'TRADING_AGENT_TYPESAFE_API_KEY'
_TEST_STATE = {
    'purpose': 'A connection test from the trading-agent doctor, not a real market state.',
    'last_price': 100.0,
}


class JevCheck(doctor_check.DoctorCheck):
    """Checks the TypeSafe API key and that Jev answers with it."""

    name = 'Jev decision model'

    def __init__(
        self,
        configuration: agent_configuration.JevConfiguration,
        secrets: secrets_module.Secrets,
        layout: workspace_layout_module.WorkspaceLayout,
        trader_names: Sequence[str],
    ):
        """Creates the check.

        Args:
            configuration (agent_configuration.JevConfiguration): How Jev is reached.
            secrets (secrets_module.Secrets): The secrets, holding the key.
            layout (workspace_layout_module.WorkspaceLayout): Where the traders' folders are.
            trader_names (Sequence[str]): The traders to look at.
        """
        self._configuration = configuration
        self._secrets = secrets
        self._layout = layout
        self._trader_names = trader_names

    def run(self) -> doctor_check.CheckResult:
        """Checks which traders use Jev, that the key is set, and that Jev answers.

        Returns:
            doctor_check.CheckResult: OK when no trader uses Jev or Jev answers, failed when a Jev trader has no key or Jev refuses it.
        """
        jev_traders = self._jev_traders()
        key = self._secrets.typesafe_api_key
        if not key and not jev_traders:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.OK,
                'No trader uses Jev.',
            )
        if not key:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'{", ".join(jev_traders)} set jev_signals, but {_VARIABLE} is not set in .env.',
            )
        client = jev_client.JevClient(self._configuration, key)
        try:
            decision = asyncio.run(client.decide(_TEST_STATE))
        except jev_client.JevError as error:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.FAILED,
                f'Jev did not answer with the key in {_VARIABLE}: {error}',
            )
        if not jev_traders:
            return doctor_check.CheckResult(
                doctor_check.CheckStatus.WARNING,
                f'Jev ({decision.model}) answers, but no trader sets jev_signals.',
            )
        return doctor_check.CheckResult(
            doctor_check.CheckStatus.OK,
            f'Jev ({decision.model}) answers, for {", ".join(jev_traders)}.',
        )

    def _jev_traders(self) -> list[str]:
        """Lists the traders whose trader.toml sets jev_signals.

        Returns:
            list[str]: Their names, in the order given.
        """
        names = []
        for name in self._trader_names:
            record_file = self._layout.trader_directory(name) / 'trader.toml'
            try:
                record = tomllib.loads(record_file.read_text(encoding='utf-8'))
            except OSError, tomllib.TOMLDecodeError:
                continue
            if record.get('jev_signals') is True:
                names.append(name)
        return names
