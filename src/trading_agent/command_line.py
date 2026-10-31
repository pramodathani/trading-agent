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
            argparse.Namespace: The parsed arguments, with `command` set to "print" when -p is given without a subcommand, and to "terminal" when neither is given.
        """
        parser = argparse.ArgumentParser(
            prog='trading-agent',
            description='An always-on, multi-trader AI trading agent.',
        )
        parser.add_argument(
            '--configuration',
            type=Path,
            default=Path('trading_agent.toml'),
            help='The configuration file to read (default: trading_agent.toml).',
        )
        parser.add_argument(
            '-p',
            '--print',
            dest='print_text',
            metavar='TEXT',
            help='Send one message or /command to the running gateway, print the reply and exit; text piped on standard input is put before it.',
        )
        parser.add_argument(
            '--trader',
            dest='chosen_trader',
            default=None,
            help='The trader that -p talks to, or that the terminal program opens on (default: general, or for the terminal program the trader used last).',
        )
        parser.add_argument(
            '--output-format',
            choices=[
                'text',
                'json',
                'stream-json',
            ],
            default='text',
            help='How -p prints the reply: text as it streams, one json object at the end, or stream-json with one event per line (default: text).',
        )
        subparsers = parser.add_subparsers(dest='command')
        subparsers.add_parser(
            'serve',
            help='Run the gateway and its traders. With no subcommand, trading-agent opens the terminal program instead.',
        )
        subparsers.add_parser(
            'doctor',
            help='Check that everything the agent needs is in place.',
        )
        send_parser = subparsers.add_parser(
            'send',
            help='Send a message to a trader of the running gateway and print the reply.',
        )
        send_parser.add_argument(
            'text',
            help='The message, or a /command such as /status.',
        )
        send_parser.add_argument(
            '--trader',
            default='general',
            help='The trader to send it to (default: general).',
        )
        traders_parser = subparsers.add_parser(
            'traders',
            help='List, create, retire and restore traders of the running gateway.',
        )
        trader_actions = traders_parser.add_subparsers(
            dest='trader_action',
            required=True,
        )
        trader_actions.add_parser(
            'list',
            help='List every trader with its state and mandate.',
        )
        new_parser = trader_actions.add_parser(
            'new',
            help='Create a trader with a mandate and start it.',
        )
        new_parser.add_argument(
            'name',
            help="The trader's name: lower-case letters, digits, hyphens and underscores, at most 200 characters.",
        )
        new_parser.add_argument(
            '--mandate',
            required=True,
            help='What the trader will trade and how.',
        )
        new_parser.add_argument(
            '--models',
            default='',
            help='The backends to use, most preferred first, separated by commas (default: the [traders] backend_order).',
        )
        new_parser.add_argument(
            '--heartbeat',
            type=int,
            default=None,
            help='Minutes between heartbeats while the market is open, or 0 for none (default: the [traders] heartbeat_minutes).',
        )
        new_parser.add_argument(
            '--checks',
            default='',
            help='India times on trading days when the trader is woken, as HH:MM separated by commas, such as 09:10,15:05.',
        )
        retire_trader_parser = trader_actions.add_parser(
            'retire',
            help='Stop a trader and mark it retired; its files stay. A trader with positions or open orders must be flattened first.',
        )
        retire_trader_parser.add_argument(
            'name',
            help='The trader.',
        )
        restore_trader_parser = trader_actions.add_parser(
            'restore',
            help='Bring a retired trader back.',
        )
        restore_trader_parser.add_argument(
            'name',
            help='The trader.',
        )
        proposals_parser = subparsers.add_parser(
            'proposals',
            help='Review the changes traders propose to your files.',
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
        checkpoints_parser = subparsers.add_parser(
            'checkpoints',
            help="List or restore snapshots of a trader's own files.",
        )
        checkpoint_actions = checkpoints_parser.add_subparsers(
            dest='checkpoint_action',
            required=True,
        )
        list_parser = checkpoint_actions.add_parser(
            'list',
            help='List the most recent checkpoints, newest first.',
        )
        list_parser.add_argument(
            '--trader',
            default='general',
            help='The trader (default: general).',
        )
        list_parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='The most checkpoints to list (default: 20).',
        )
        restore_parser = checkpoint_actions.add_parser(
            'restore',
            help="Put the trader's Memory.md, memory/ and notes/ back as they were at a checkpoint.",
        )
        restore_parser.add_argument(
            'checkpoint_id',
            help='The checkpoint id from the list.',
        )
        restore_parser.add_argument(
            '--trader',
            default='general',
            help='The trader (default: general).',
        )
        skills_parser = subparsers.add_parser(
            'skills',
            help='List skills, or import skills into workspace/shared/skills/installed.',
        )
        skill_actions = skills_parser.add_subparsers(
            dest='skill_action',
            required=True,
        )
        skill_actions.add_parser(
            'list',
            help="List each trader's usable and hidden skills.",
        )
        import_parser = skill_actions.add_parser(
            'import',
            help='Import every skill found in a folder, a .zip file or a git URL.',
        )
        import_parser.add_argument(
            'source',
            help='The folder, .zip file or git URL.',
        )
        import_parser.add_argument(
            '--replace',
            action='store_true',
            help='Replace installed skills that have the same name.',
        )
        mcp_parser = subparsers.add_parser(
            'mcp',
            help='Check the MCP servers in mcp_servers.json.',
        )
        mcp_actions = mcp_parser.add_subparsers(
            dest='mcp_action',
            required=True,
        )
        mcp_actions.add_parser(
            'list',
            help='Connect to every MCP server once and list its tools.',
        )
        packages_parser = subparsers.add_parser(
            'packages',
            help='Install, list or remove packages of skills, subagents, MCP servers, hooks and apps.',
        )
        package_actions = packages_parser.add_subparsers(
            dest='package_action',
            required=True,
        )
        package_install_parser = package_actions.add_parser(
            'install',
            help='Install a package from a folder, a .zip file or a git URL.',
        )
        package_install_parser.add_argument(
            'source',
            help='The folder, .zip file or git URL.',
        )
        package_install_parser.add_argument(
            '--replace',
            action='store_true',
            help='Replace an installed package that has the same name.',
        )
        package_actions.add_parser('list', help='List the installed packages.')
        package_remove_parser = package_actions.add_parser(
            'remove',
            help='Remove an installed package.',
        )
        package_remove_parser.add_argument(
            'name',
            help='The package name from the list.',
        )
        subagents_parser = subparsers.add_parser(
            'subagents',
            help='Check the subagent definitions in workspace/shared/agents and packages.',
        )
        subagent_actions = subagents_parser.add_subparsers(
            dest='subagent_action',
            required=True,
        )
        subagent_actions.add_parser(
            'list',
            help='List every subagent with its model, tools and limits.',
        )
        subparsers.add_parser(
            'preflight',
            help='Run every doctor check plus the going-live checks, and say whether trading-agent is ready to trade live.',
        )
        apps_parser = subparsers.add_parser(
            'apps',
            help="List the packages' web apps, and set up their systemd units.",
        )
        app_actions = apps_parser.add_subparsers(
            dest='app_action',
            required=True,
        )
        app_actions.add_parser(
            'list',
            help='List each app, whether it answers and its unit state.',
        )
        enable_parser = app_actions.add_parser(
            'enable',
            help="Link, enable and start an app's systemd user unit.",
        )
        enable_parser.add_argument(
            'package', help='The package whose app to enable.'
        )
        disable_parser = app_actions.add_parser(
            'disable',
            help="Stop an app's unit and stop it starting at login.",
        )
        disable_parser.add_argument(
            'package', help='The package whose app to disable.'
        )
        pairing_parser = subparsers.add_parser(
            'pairing',
            help='Manage the Telegram chats allowed to command the traders.',
        )
        pairing_actions = pairing_parser.add_subparsers(
            dest='pairing_action',
            required=True,
        )
        pairing_actions.add_parser(
            'list',
            help='List the paired chats and the codes waiting for approval.',
        )
        approve_parser = pairing_actions.add_parser(
            'approve',
            help='Pair the chat that the bot gave this code.',
        )
        approve_parser.add_argument(
            'code', help='The eight-character code the bot sent.'
        )
        revoke_parser = pairing_actions.add_parser(
            'revoke',
            help='Unpair a chat, so the bot ignores it.',
        )
        revoke_parser.add_argument(
            'chat_id', help='The chat id that `pairing list` shows.'
        )
        arguments = parser.parse_args(argument_list)
        if arguments.command is None and arguments.print_text is not None:
            arguments.command = 'print'
        if arguments.command is None:
            arguments.command = 'terminal'
        return arguments
