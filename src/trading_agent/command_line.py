"""Reads the command-line arguments of `trading-agent`.

Typical usage example:

  arguments = CommandLine().parse(['doctor'])
  arguments.command  # 'doctor'
"""

import argparse
from collections.abc import Sequence
from pathlib import Path


class CommandLine:
    """The `trading-agent` command and its subcommands."""

    def parse(
        self, argument_list: Sequence[str] | None = None
    ) -> argparse.Namespace:
        """Parses the arguments.

        Args:
            argument_list (Sequence[str] | None): The arguments to parse, or None to read them from sys.argv.

        Returns:
            argparse.Namespace: The parsed arguments, with `command` set to "serve" when no subcommand is given.
        """
        parser = argparse.ArgumentParser(
            prog='trading-agent',
            description='An always-on, multi-desk AI trading agent.',
        )
        parser.add_argument(
            '--configuration',
            type=Path,
            default=Path('trading_agent.toml'),
            help='The configuration file to read (default: trading_agent.toml).',
        )
        subparsers = parser.add_subparsers(dest='command')
        subparsers.add_parser('serve', help='Run the gateway and its desks.')
        subparsers.add_parser(
            'doctor',
            help='Check that everything the agent needs is in place.',
        )
        arguments = parser.parse_args(argument_list)
        if arguments.command is None:
            arguments.command = 'serve'
        return arguments
