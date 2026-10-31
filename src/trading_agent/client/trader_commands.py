"""The `trading-agent traders` commands: list, create, retire and restore traders through the running gateway.

They talk to the gateway rather than writing the traders' folders themselves, because the gateway owns the running traders: a new trader must be built and started inside it, and a retired one stopped there.

Typical usage example:

  commands = TraderCommands('http://127.0.0.1:8120', token)
  exit_code = asyncio.run(commands.create('banknifty-momentum', 'Intraday momentum in Bank Nifty options, buying only', '', None, ''))
"""

import sys
from typing import Any, TextIO

from trading_agent.terminal import gateway_client


class TraderCommands:
    """Changes which traders exist, for the user at a terminal."""

    def __init__(
        self,
        base_url: str,
        access_token: str,
        output: TextIO = sys.stdout,
    ):
        """Creates the commands.

        Args:
            base_url (str): The gateway's address, such as http://127.0.0.1:8120.
            access_token (str): The gateway's access token.
            output (TextIO): Where to print.
        """
        self._base_url = base_url
        self._access_token = access_token
        self._output = output

    async def list(self) -> int:
        """Prints every trader with its state, schedule and mandate.

        Returns:
            int: 0 when the gateway answered, 1 otherwise.
        """
        try:
            async with self._gateway() as gateway:
                records = (await gateway.trader_records())['records']
        except gateway_client.GatewayError as error:
            return self._problem(error)
        for record in records:
            state = 'running'
            if record['retired']:
                state = 'retired'
            elif not record['running']:
                state = 'not running'
            self._print(f'{record["name"]} ({state}): {record["mandate"]}')
            self._print(f'  {self._schedule_text(record)}')
        return 0

    async def create(
        self,
        name: str,
        mandate: str,
        models: str,
        heartbeat_minutes: int | None,
        checks: str,
    ) -> int:
        """Creates a trader, which then introduces itself on the web page and in Telegram.

        Args:
            name (str): The trader's name.
            mandate (str): What it will trade and how.
            models (str): The backends to use, separated by commas, or an empty string for the defaults.
            heartbeat_minutes (int | None): Minutes between heartbeats, 0 for none, or None for the default.
            checks (str): The scheduled check times, as HH:MM separated by commas, or an empty string for none.

        Returns:
            int: 0 when it was created, 1 otherwise.
        """
        try:
            async with self._gateway() as gateway:
                record = await gateway.create_trader(
                    {
                        'name': name,
                        'mandate': mandate,
                        'backend_order': self._split(models),
                        'heartbeat_minutes': heartbeat_minutes,
                        'scheduled_checks': self._split(checks),
                    }
                )
        except gateway_client.GatewayError as error:
            return self._problem(error)
        self._print(
            f'Created {record["name"]}. It is reading its mandate now; its first reply will appear on the web page and in Telegram, or ask it with: trading-agent send --trader {record["name"]} "..."'
        )
        return 0

    async def retire(self, name: str) -> int:
        """Retires a trader.

        Args:
            name (str): The trader.

        Returns:
            int: 0 when it was retired, 1 otherwise.
        """
        try:
            async with self._gateway() as gateway:
                await gateway.retire_trader(name)
        except gateway_client.GatewayError as error:
            return self._problem(error)
        self._print(
            f'Retired {name}. Its files stay; bring it back with: trading-agent traders restore {name}'
        )
        return 0

    async def restore(self, name: str) -> int:
        """Brings a retired trader back.

        Args:
            name (str): The trader.

        Returns:
            int: 0 when it is running again, 1 otherwise.
        """
        try:
            async with self._gateway() as gateway:
                await gateway.restore_trader(name)
        except gateway_client.GatewayError as error:
            return self._problem(error)
        self._print(f'{name} is running again, with its memory and sessions.')
        return 0

    @staticmethod
    def _split(text: str) -> list[str]:
        """Splits a comma-separated option into its non-empty parts.

        Args:
            text (str): The option, such as "claude, deepseek".

        Returns:
            list[str]: The parts, stripped of spaces.
        """
        parts = []
        for part in text.split(','):
            if part.strip():
                parts.append(part.strip())
        return parts

    @staticmethod
    def _schedule_text(record: dict[str, Any]) -> str:
        """Describes a trader's models and schedule in one line.

        Args:
            record (dict[str, Any]): The trader's record from the gateway.

        Returns:
            str: Its models, heartbeat and scheduled checks.
        """
        models = ', '.join(record['backend_order']) or 'none'
        heartbeat = 'no heartbeat'
        if record['heartbeat_minutes']:
            heartbeat = f'heartbeat every {record["heartbeat_minutes"]} min'
        checks = ', '.join(record['scheduled_checks']) or 'none'
        return f'models: {models}; {heartbeat}; checks: {checks}'

    def _gateway(self) -> gateway_client.GatewayClient:
        """Opens a client for the gateway.

        Returns:
            gateway_client.GatewayClient: The client, used as an async context manager.
        """
        return gateway_client.GatewayClient(self._base_url, self._access_token)

    def _problem(self, error: gateway_client.GatewayError) -> int:
        """Prints why a command failed.

        Args:
            error (gateway_client.GatewayError): The gateway's error.

        Returns:
            int: 1, the exit status for a failure.
        """
        if error.status_code == 0:
            print(
                f'The gateway at {self._base_url} does not answer: {error.message}. Start it with `systemctl --user start trading-agent`.',
                file=sys.stderr,
            )
            return 1
        print(error.message, file=sys.stderr)
        return 1

    def _print(self, line: Any) -> None:
        """Prints one line.

        Args:
            line (Any): The line.

        Returns:
            None.
        """
        print(line, file=self._output)
