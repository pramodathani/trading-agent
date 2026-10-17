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
        checkpoints_parser = subparsers.add_parser(
            'checkpoints',
            help="List or restore snapshots of a desk's own files.",
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
            '--desk',
            default='main',
            help='The desk (default: main).',
        )
        list_parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='The most checkpoints to list (default: 20).',
        )
        restore_parser = checkpoint_actions.add_parser(
            'restore',
            help="Put the desk's Memory.md, memory/ and notes/ back as they were at a checkpoint.",
        )
        restore_parser.add_argument(
            'checkpoint_id',
            help='The checkpoint id from the list.',
        )
        restore_parser.add_argument(
            '--desk',
            default='main',
            help='The desk (default: main).',
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
            help="List each desk's usable and hidden skills.",
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
            help='Manage the Telegram chats allowed to command the desks.',
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
        if arguments.command is None:
            arguments.command = 'serve'
        return arguments
