"""Describes tool calls in plain words: what one is doing now, and a summary of several once done.

It is a port of the web page's toolDescriber.ts, so the terminal and the browser use the same words.

Typical usage example:

  describer = ToolDescriber()
  describer.activity('get_quote')  # 'Fetching a quote'
  describer.summary([('get_quote', False), ('bash_run', True)])
"""

import json
from collections.abc import Sequence

_KINDS = {
    'command': (
        'ran a command',
        'ran {count} commands',
    ),
    'read': (
        'read a file',
        'read {count} files',
    ),
    'write': (
        'edited a file',
        'edited {count} files',
    ),
    'picture': (
        'looked at a picture',
        'looked at {count} pictures',
    ),
    'search': (
        'made a search',
        'made {count} searches',
    ),
    'web': (
        'read a web page',
        'read {count} web pages',
    ),
    'browser': (
        'took a browser step',
        'took {count} browser steps',
    ),
    'quote': (
        'fetched a quote',
        'fetched {count} quotes',
    ),
    'market': (
        'read market data',
        'read market data {count} times',
    ),
    'account': (
        'checked the account',
        'checked the account {count} times',
    ),
    'order': (
        'sent an order action',
        'sent {count} order actions',
    ),
    'message': (
        'sent a message',
        'sent {count} messages',
    ),
    'skill': (
        'used a skill',
        'used {count} skills',
    ),
    'schedule': (
        'changed a schedule or alert',
        'changed {count} schedules or alerts',
    ),
    'subagent': (
        'delegated a task',
        'delegated {count} tasks',
    ),
    'tool': (
        'used a tool',
        'used {count} tools',
    ),
}
_TOOLS = {
    'bash_run': (
        'Running a command',
        'command',
    ),
    'bash_background': (
        'Starting a background command',
        'command',
    ),
    'bash_check': (
        'Checking a background command',
        'command',
    ),
    'bash_restart': (
        'Restarting the shell',
        'command',
    ),
    'read_file': (
        'Reading a file',
        'read',
    ),
    'write_file': (
        'Writing a file',
        'write',
    ),
    'edit_file': (
        'Editing a file',
        'write',
    ),
    'add_note': (
        'Writing a note',
        'write',
    ),
    'propose_file_change': (
        'Proposing a file change',
        'write',
    ),
    'view_image': (
        'Looking at a picture',
        'picture',
    ),
    'web_search': (
        'Searching the web',
        'search',
    ),
    'search_knowledge': (
        'Searching the knowledge base',
        'search',
    ),
    'search_sessions': (
        'Searching past sessions',
        'search',
    ),
    'search_instruments': (
        'Looking up instruments',
        'search',
    ),
    'tool_search': (
        'Looking for a tool',
        'search',
    ),
    'web_fetch': (
        'Reading a web page',
        'web',
    ),
    'browser_open': (
        'Opening a page in the browser',
        'browser',
    ),
    'browser_snapshot': (
        'Reading the browser page',
        'browser',
    ),
    'browser_click': (
        'Clicking in the browser',
        'browser',
    ),
    'browser_type': (
        'Typing in the browser',
        'browser',
    ),
    'browser_screenshot': (
        'Taking a browser screenshot',
        'browser',
    ),
    'browser_back': (
        'Going back in the browser',
        'browser',
    ),
    'browser_tabs': (
        'Checking browser tabs',
        'browser',
    ),
    'get_quote': (
        'Fetching a quote',
        'quote',
    ),
    'get_candles': (
        'Reading price candles',
        'market',
    ),
    'get_time': (
        'Checking the time',
        'market',
    ),
    'get_portfolio': (
        'Checking the portfolio',
        'account',
    ),
    'get_orders': (
        'Checking orders',
        'account',
    ),
    'place_order': (
        'Placing an order',
        'order',
    ),
    'place_bracket_order': (
        'Placing a bracket order',
        'order',
    ),
    'modify_order': (
        'Modifying an order',
        'order',
    ),
    'cancel_order': (
        'Cancelling an order',
        'order',
    ),
    'flatten_desk': (
        "Closing the desk's positions",
        'order',
    ),
    'send_message': (
        'Sending a message',
        'message',
    ),
    'send_image': (
        'Sending a picture',
        'message',
    ),
    'load_skill': (
        'Loading a skill',
        'skill',
    ),
    'skill_create': (
        'Writing a new skill',
        'skill',
    ),
    'skill_patch': (
        'Updating a skill',
        'skill',
    ),
    'skill_archive': (
        'Archiving a skill',
        'skill',
    ),
    'cron_create': (
        'Scheduling a job',
        'schedule',
    ),
    'cron_list': (
        'Listing scheduled jobs',
        'schedule',
    ),
    'cron_delete': (
        'Removing a scheduled job',
        'schedule',
    ),
    'schedule_wakeup': (
        'Setting a wake-up',
        'schedule',
    ),
    'set_price_alert': (
        'Setting a price alert',
        'schedule',
    ),
    'cancel_price_alert': (
        'Cancelling a price alert',
        'schedule',
    ),
    'delegate_task': (
        'Handing work to a subagent',
        'subagent',
    ),
    'call_mcp_tool': (
        'Using an MCP tool',
        'tool',
    ),
}
_DETAIL_KEYS = (
    'command',
    'symbol',
    'query',
    'keywords',
    'path',
    'file_path',
    'url',
    'skill_name',
    'tool_name',
    'name',
)
_DETAIL_LENGTH = 48


class ToolDescriber:
    """Words for tool calls, keyed by tool name."""

    def activity(self, tool_name: str) -> str:
        """What a running tool is doing.

        Args:
            tool_name (str): The tool's name, with or without Claude Code's MCP prefix.

        Returns:
            str: Such as "Fetching a quote", or "Using <name>" for a tool without its own words.
        """
        known = _TOOLS.get(self.base_name(tool_name))
        if known is None:
            return f'Using {tool_name}'
        return known[0]

    def detail(self, arguments_text: str) -> str:
        """The most telling argument of a tool call, shortened.

        Args:
            arguments_text (str): The call's arguments as JSON text.

        Returns:
            str: Such as "RELIANCE" or "ls -la", or an empty string when there is none.
        """
        try:
            values = json.loads(arguments_text)
        except ValueError:
            return ''
        if not isinstance(values, dict):
            return ''
        for key in _DETAIL_KEYS:
            value = values.get(key)
            if isinstance(value, str) and value.strip():
                line = value.strip().split('\n')[0]
                if len(line) > _DETAIL_LENGTH:
                    return line[: _DETAIL_LENGTH - 1] + '…'
                return line
        return ''

    def summary(self, calls: Sequence[tuple[str, bool]]) -> str:
        """One line summing up several tool calls, as Claude Code does.

        Args:
            calls (Sequence[tuple[str, bool]]): Each call's tool name and whether it failed, in order.

        Returns:
            str: Such as "Fetched 2 quotes, ran a command (1 failed)".
        """
        order = []
        counts = {}
        failures = {}
        for tool_name, failed in calls:
            kind = 'tool'
            known = _TOOLS.get(self.base_name(tool_name))
            if known is not None:
                kind = known[1]
            if kind not in counts:
                order.append(kind)
                counts[kind] = 0
                failures[kind] = 0
            counts[kind] += 1
            if failed:
                failures[kind] += 1
        parts = []
        for kind in order:
            one, many = _KINDS[kind]
            part = one
            if counts[kind] > 1:
                part = many.replace('{count}', str(counts[kind]))
            if failures[kind] > 0:
                part = f'{part} ({failures[kind]} failed)'
            parts.append(part)
        sentence = ', '.join(parts)
        return sentence[:1].upper() + sentence[1:]

    def base_name(self, tool_name: str) -> str:
        """A tool's own name without the prefix Claude Code adds to tools served over MCP.

        Args:
            tool_name (str): The name as the event gives it.

        Returns:
            str: Such as "get_quote" for "mcp__trading_agent__get_quote".
        """
        return tool_name.split('__')[-1]
