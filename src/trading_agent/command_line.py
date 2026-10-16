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
        send_parser = subparsers.add_parser(
            'send',
            help='Send a message to a desk of the running gateway and print the reply.',
        )
        send_parser.add_argument(
            'text',
            help='The message, or a /command such as /status.',
        )
        send_parser.add_argument(
            '--desk',
            default='main',
            help='The desk to send it to (default: main).',
        )
        proposals_parser = subparsers.add_parser(
            'proposals',
            help='Review the changes desks propose to your files.',
        )
        proposal_actions = proposals_parser.add_subparsers(
            dest='proposal_action',
            required=True,
        )
        proposal_actions.add_parser('list', help='List every proposal.')
        for action, action_help in [
            ('show', 'Show what a proposal would change.'),
            (
                'accept',
                'Apply a proposal to its file, keeping a copy of the old file.',
            ),
            ('reject', 'Reject a proposal without changing any file.'),
        ]:
            action_parser = proposal_actions.add_parser(
                action, help=action_help
            )
            action_parser.add_argument(
                'proposal_id', help='The proposal id from the list.'
            )
        arguments = parser.parse_args(argument_list)
        if arguments.command is None:
            arguments.command = 'serve'
        return arguments
