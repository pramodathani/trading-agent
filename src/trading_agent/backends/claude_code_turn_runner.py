"""Runs a desk's turns on Claude through Claude Code and the Max subscription.

Claude Code runs the agent loop itself, so this is a turn runner rather than a ModelBackend. It keeps one Claude Code session per desk, so Claude remembers earlier turns. It is set up so that it never stops for a human:

- permission_mode is bypassPermissions and setting_sources is empty, so no "ask" rule from any settings file applies;
- the subscription token from `claude setup-token` is passed as CLAUDE_CODE_OAUTH_TOKEN;
- every built-in Claude Code tool is switched off, and a PreToolUse hook allows only trading-agent's tools.

Before each turn the runner asks Claude Code how full the session's context is. At 70% of the window it gives Claude a memory-flush turn and then sends `/compact`, so Claude saves what matters before the older turns are summarised. Claude Code's own automatic compaction stays on as a safety net for one very long turn, set to fire at about 82% by limiting the window it measures against.

Typical usage example:

  runner = ClaudeCodeTurnRunner('main', 'claude', backend_configuration, bridge, event_bus, settings)
  result = await runner.run_turn(trigger)
"""

import asyncio
import dataclasses
import logging
import os
from pathlib import Path
from typing import Any

import claude_agent_sdk

from trading_agent.agent import context_compressor
from trading_agent.agent import prompt_builder as prompt_builder_module
from trading_agent.backends import backend as backend_module
from trading_agent.backends import claude_pre_compact_hook
from trading_agent.backends import claude_steering_hook
from trading_agent.backends import claude_tool_allowlist_hook
from trading_agent.backends import claude_tool_bridge
from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import steering_inbox as steering_inbox_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner

_LOGGER = logging.getLogger(__name__)
_API_KEY_VARIABLE = 'ANTHROPIC_API_KEY'
_REJECTED = 'rejected'
_TRADINGMACHINE_PREFIX = 'TRADINGMACHINE_'
_MCP_TOOL_TIMEOUT_MILLISECONDS = 2_000_000


@dataclasses.dataclass(frozen=True)
class ClaudeCodeSettings:
    """The settings of one Claude Code session that do not come from the backend's table.

    Attributes:
        prompt_builder: Builds the desk's instructions before every turn.
        oauth_token: The subscription token from `claude setup-token`.
        working_directory: The folder Claude Code runs in.
        maximum_rounds: The most model calls one turn may make.
        sessions_directory: Where Claude Code keeps its sessions, normally ~/.claude/projects, checked before a saved session is resumed.
        compression_threshold: The share of the context window at which the session is flushed and compacted before a turn.
        emergency_compression_threshold: The share of the window given to Claude Code as its own compaction window, the safety net for one long turn.
    """

    prompt_builder: prompt_builder_module.PromptBuilder
    oauth_token: str
    working_directory: Path
    maximum_rounds: int
    sessions_directory: Path
    compression_threshold: float
    emergency_compression_threshold: float


class ClaudeCodeTurnRunner(turn_runner.TurnRunner):
    """One desk's Claude Code session.

    Attributes:
        session_id: Claude Code's session identifier, known after the first turn.
    """

    def __init__(
        self,
        desk_name: str,
        backend_name: str,
        backend_configuration: agent_configuration.BackendConfiguration,
        bridge: claude_tool_bridge.ClaudeToolBridge,
        event_bus: event_bus_module.EventBus,
        settings: ClaudeCodeSettings,
        steering_inbox: steering_inbox_module.SteeringInbox | None = None,
    ):
        """Creates the runner without starting Claude Code.

        Args:
            desk_name (str): The desk the session belongs to.
            backend_name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings, of kind "claude_code".
            bridge (claude_tool_bridge.ClaudeToolBridge): The desk's tools, as Claude Code sees them.
            event_bus (event_bus_module.EventBus): Where every step is published.
            settings (ClaudeCodeSettings): The prompt, token, folder and round limit.
            steering_inbox (steering_inbox_module.SteeringInbox | None): The desk's mid-turn messages, handed to Claude after each tool call, or None.
        """
        self._desk_name = desk_name
        self._backend_name = backend_name
        self._model = backend_configuration.model
        self._context_window = backend_configuration.context_window
        self._bridge = bridge
        self._event_bus = event_bus
        self._settings = settings
        self._steering_inbox = steering_inbox
        self._client = None
        self._session_prompt_fingerprint = None
        self.session_id: str | None = None

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Sends the trigger to Claude and waits for its final answer.

        Args:
            trigger (trigger_module.Trigger): The reason for the turn.

        Returns:
            turn_runner.TurnResult: Claude's final text.

        Raises:
            backend_module.BackendUnavailableError: Claude cannot be used now: no token, an API key is set, the subscription limit is reached, or Claude Code failed.
        """
        self._check_preconditions()
        self._bridge.executor.start_turn()
        self._bridge.current_trigger = trigger
        prompt = self._settings.prompt_builder.build()
        try:
            client = await self._connected_client(prompt)
            await self._compact_if_full(client, trigger)
            await client.query(self._query_text(prompt, trigger))
            self._session_prompt_fingerprint = prompt.fingerprint
            return await self._read_response(client, trigger)
        except asyncio.CancelledError:
            await self._disconnect()
            raise
        except backend_module.BackendUnavailableError:
            await self._disconnect()
            raise
        except claude_agent_sdk.ClaudeSDKError as error:
            await self._disconnect()
            raise backend_module.BackendUnavailableError(
                f'Claude Code failed: {error!r}'
            ) from error

    async def compact(self, trigger: trigger_module.Trigger) -> str:
        """Flushes and compacts the session now, for the /compact command.

        Args:
            trigger (trigger_module.Trigger): The command's trigger, used to tag events.

        Returns:
            str: What happened, for the user.

        Raises:
            backend_module.BackendUnavailableError: Claude cannot be used now.
        """
        if self.session_id is None:
            return 'Claude has no session yet, so there is nothing to compact.'
        self._check_preconditions()
        self._bridge.executor.start_turn()
        prompt = self._settings.prompt_builder.build()
        try:
            client = await self._connected_client(prompt)
            usage = await client.get_context_usage()
            after = await self._flush_and_compact(
                client,
                trigger,
                'command',
                usage['totalTokens'],
            )
        except backend_module.BackendUnavailableError:
            await self._disconnect()
            raise
        except claude_agent_sdk.ClaudeSDKError as error:
            await self._disconnect()
            raise backend_module.BackendUnavailableError(
                f'Claude Code failed: {error!r}'
            ) from error
        return f"Compacted Claude's session from {usage['totalTokens']:,} to {after:,} tokens, after a memory-flush turn."

    def note_compaction(self) -> None:
        """Remembers that the session was compacted, so the next turn sends the instruction files again.

        Updated instructions delivered inside earlier messages may not survive a compaction, so the next turn's message carries the complete current version.
        """
        self._session_prompt_fingerprint = None

    async def _compact_if_full(
        self,
        client: claude_agent_sdk.ClaudeSDKClient,
        trigger: trigger_module.Trigger,
    ) -> None:
        """Flushes and compacts the session when it fills the configured share of the window.

        Args:
            client (claude_agent_sdk.ClaudeSDKClient): The connected client.
            trigger (trigger_module.Trigger): The turn about to run.
        """
        if self.session_id is None:
            return
        usage = await client.get_context_usage()
        limit = self._settings.compression_threshold * self._context_window
        if usage['totalTokens'] < limit:
            return
        await self._flush_and_compact(
            client,
            trigger,
            'threshold',
            usage['totalTokens'],
        )

    async def _flush_and_compact(
        self,
        client: claude_agent_sdk.ClaudeSDKClient,
        trigger: trigger_module.Trigger,
        reason: str,
        tokens_before: int,
    ) -> int:
        """Gives Claude a memory-flush turn, then compacts the session with instructions on what to keep.

        Args:
            client (claude_agent_sdk.ClaudeSDKClient): The connected client.
            trigger (trigger_module.Trigger): The trigger that caused it, used to tag the event.
            reason (str): "threshold" or "command", for the event.
            tokens_before (int): The session's size before, for the event.

        Returns:
            int: The session's size afterwards, in tokens.
        """
        flush_trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.COMPRESSION,
            self._desk_name,
            context_compressor.FLUSH_REQUEST,
        )
        self._bridge.current_trigger = flush_trigger
        await client.query(context_compressor.FLUSH_REQUEST)
        await self._read_response(client, flush_trigger)
        await client.query(f'/compact Keep {context_compressor.SUMMARY_FOCUS}.')
        await self._read_response(client, flush_trigger)
        self._bridge.current_trigger = trigger
        self.note_compaction()
        usage = await client.get_context_usage()
        self._publish(
            event_module.EventKind.CONTEXT_COMPRESSED,
            {
                'trigger_id': trigger.trigger_id,
                'backend': self._backend_name,
                'reason': reason,
                'tokens_before': tokens_before,
                'tokens_after': usage['totalTokens'],
                'context_window': self._context_window,
            },
        )
        return usage['totalTokens']

    def _check_preconditions(self) -> None:
        """Refuses to run when the run would not use the subscription.

        Raises:
            backend_module.BackendUnavailableError: An ANTHROPIC_API_KEY is set, which Claude Code would bill instead, or the subscription token is missing.
        """
        if _API_KEY_VARIABLE in os.environ:
            raise backend_module.BackendUnavailableError(
                'ANTHROPIC_API_KEY is set, so Claude Code would bill the API instead of the Max subscription; unset it.'
            )
        if not self._settings.oauth_token:
            raise backend_module.BackendUnavailableError(
                'TRADING_AGENT_CLAUDE_CODE_OAUTH_TOKEN is not set in .env.'
            )

    async def _connected_client(
        self,
        prompt: prompt_builder_module.SystemPrompt,
    ) -> claude_agent_sdk.ClaudeSDKClient:
        """Returns the session's client, starting Claude Code if it is not running.

        A process started after a failure resumes the previous session, so Claude keeps its memory of earlier turns. A brand-new session starts with the current prompt.

        Args:
            prompt (prompt_builder_module.SystemPrompt): The current prompt, used when a new session starts.

        Returns:
            claude_agent_sdk.ClaudeSDKClient: A connected client.
        """
        if self._client is None:
            if self.session_id is None:
                self._session_prompt_fingerprint = prompt.fingerprint
            client = claude_agent_sdk.ClaudeSDKClient(
                options=self._options(prompt.text)
            )
            await client.connect()
            self._client = client
        return self._client

    def _query_text(
        self,
        prompt: prompt_builder_module.SystemPrompt,
        trigger: trigger_module.Trigger,
    ) -> str:
        """The text to send for a turn, with updated instructions in front when the files changed.

        A resumed Claude Code session keeps the system prompt it started with and ignores a new one, so changed workspace files are delivered inside the message instead. Once sent, they are part of the session and survive a later resume. After a compaction they are sent again, because the summary may have dropped them.

        Args:
            prompt (prompt_builder_module.SystemPrompt): The current prompt.
            trigger (trigger_module.Trigger): The turn's trigger.

        Returns:
            str: The trigger's text, preceded by the updated instructions when they changed since the session last saw them.
        """
        if prompt.fingerprint == self._session_prompt_fingerprint:
            return trigger.text
        return '\n'.join(
            [
                '[The complete current versions of your instruction files follow, because they changed or this session was compacted since you last saw them. They replace the versions in your system prompt and in any earlier update; follow these from now on.]',
                prompt.text,
                '[End of the updated instructions. The trigger follows.]',
                '',
                trigger.text,
            ]
        )

    def _options(self, prompt_text: str) -> claude_agent_sdk.ClaudeAgentOptions:
        """Builds the options that keep Claude Code on the subscription and away from prompts.

        Args:
            prompt_text (str): The system prompt.

        Returns:
            claude_agent_sdk.ClaudeAgentOptions: The session's options.
        """
        self._settings.working_directory.mkdir(parents=True, exist_ok=True)
        allowed_tool_names = self._bridge.claude_tool_names()
        allowlist_hook = claude_tool_allowlist_hook.ClaudeToolAllowlistHook(
            allowed_tool_names
        )
        pre_compact_hook = claude_pre_compact_hook.ClaudePreCompactHook(
            self._desk_name,
            self._backend_name,
            self._event_bus,
            self.note_compaction,
        )
        return claude_agent_sdk.ClaudeAgentOptions(
            system_prompt=prompt_text,
            model=self._model,
            tools=[],
            mcp_servers={
                claude_tool_bridge.SERVER_NAME: self._bridge.build_server(),
            },
            allowed_tools=allowed_tool_names,
            hooks={
                'PreToolUse': [
                    claude_agent_sdk.HookMatcher(
                        hooks=[
                            allowlist_hook,
                        ],
                    ),
                ],
                'PreCompact': [
                    claude_agent_sdk.HookMatcher(
                        hooks=[
                            pre_compact_hook,
                        ],
                    ),
                ],
                'PostToolUse': [
                    claude_agent_sdk.HookMatcher(
                        hooks=self._post_tool_hooks(),
                    ),
                ],
            },
            permission_mode='bypassPermissions',
            setting_sources=[],
            include_partial_messages=True,
            max_turns=self._settings.maximum_rounds,
            cwd=self._settings.working_directory,
            env=self._environment(),
            resume=self.session_id,
            stderr=self._log_stderr,
        )

    def _post_tool_hooks(self) -> list[claude_steering_hook.ClaudeSteeringHook]:
        """The hooks that run after each tool call.

        Returns:
            list[claude_steering_hook.ClaudeSteeringHook]: The steering hook, or nothing when the desk has no steering inbox.
        """
        if self._steering_inbox is None:
            return []
        return [
            claude_steering_hook.ClaudeSteeringHook(self._steering_inbox),
        ]

    def _environment(self) -> dict[str, str]:
        """The environment variables Claude Code gets on top of the gateway's.

        The SDK copies the gateway's whole environment into Claude Code and can only add or replace variables. tradingmachine copies its settings, including the MongoDB password, into the gateway's environment when it loads its .env file, so every TRADINGMACHINE_ variable is replaced with an empty value.

        CLAUDE_CODE_AUTO_COMPACT_WINDOW makes Claude Code measure its automatic compaction against a smaller window; it compacts 33,000 tokens below that window, so 850,000 of 1,000,000 fires at 817,000. CLAUDE_AUTOCOMPACT_PCT_OVERRIDE, which the plan named, did not change the threshold Claude Code reports, so it is not used.

        MCP_TOOL_TIMEOUT gives one call of trading-agent's tools up to 2,000 seconds, because delegate_task can wait for a subagent for up to 30 minutes; Claude Code's own default is not documented. Each tool still has its own, shorter limit inside trading-agent.

        Returns:
            dict[str, str]: The subscription token, the automatic compaction window, the tool timeout, and an empty value for each tradingmachine setting.
        """
        compaction_window = int(
            self._settings.emergency_compression_threshold
            * self._context_window
        )
        environment = {
            'CLAUDE_CODE_OAUTH_TOKEN': self._settings.oauth_token,
            'CLAUDE_CODE_AUTO_COMPACT_WINDOW': str(compaction_window),
            'MCP_TOOL_TIMEOUT': str(_MCP_TOOL_TIMEOUT_MILLISECONDS),
        }
        for name in os.environ:
            if name.startswith(_TRADINGMACHINE_PREFIX):
                environment[name] = ''
        return environment

    async def _read_response(
        self,
        client: claude_agent_sdk.ClaudeSDKClient,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Reads Claude Code's messages for one turn, publishing each step.

        Args:
            client (claude_agent_sdk.ClaudeSDKClient): The connected client.
            trigger (trigger_module.Trigger): The turn's trigger.

        Returns:
            turn_runner.TurnResult: Claude's final text.

        Raises:
            backend_module.BackendUnavailableError: The subscription limit was hit, or the turn ended in an error.
        """
        last_text = ''
        async for message in client.receive_response():
            if isinstance(message, claude_agent_sdk.StreamEvent):
                self._publish_stream_event(trigger, message.event)
            elif isinstance(message, claude_agent_sdk.RateLimitEvent):
                self._handle_rate_limit(trigger, message.rate_limit_info)
            elif isinstance(message, claude_agent_sdk.AssistantMessage):
                if message.error is not None:
                    raise backend_module.BackendUnavailableError(
                        f'Claude answered with an error: {message.error}'
                    )
                text = self._text_of(message)
                if text:
                    last_text = text
            elif isinstance(message, claude_agent_sdk.ResultMessage):
                self.session_id = message.session_id
                self._publish_usage(trigger, message)
                if message.is_error:
                    raise backend_module.BackendUnavailableError(
                        f'Claude Code turn failed: {message.subtype} {message.result}'
                    )
                if message.result:
                    last_text = message.result
        return turn_runner.TurnResult(text=last_text)

    def _publish_stream_event(
        self,
        trigger: trigger_module.Trigger,
        stream_event: dict[str, Any],
    ) -> None:
        """Publishes the text pieces of Claude's streamed reply.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.
            stream_event (dict[str, Any]): A raw stream event from the Messages API.
        """
        if stream_event.get('type') != 'content_block_delta':
            return
        delta = stream_event.get('delta', {})
        if delta.get('type') != 'text_delta':
            return
        self._publish(
            event_module.EventKind.TEXT_DELTA,
            {
                'trigger_id': trigger.trigger_id,
                'text': delta.get('text', ''),
            },
        )

    def _handle_rate_limit(
        self,
        trigger: trigger_module.Trigger,
        rate_limit_info: claude_agent_sdk.RateLimitInfo,
    ) -> None:
        """Publishes the subscription's limit status, and gives up when it is reached.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.
            rate_limit_info (claude_agent_sdk.RateLimitInfo): The status Claude Code reported.

        Raises:
            backend_module.BackendUnavailableError: The limit has been reached.
        """
        self._publish(
            event_module.EventKind.RATE_LIMIT,
            {
                'trigger_id': trigger.trigger_id,
                'backend': self._backend_name,
                'status': rate_limit_info.status,
                'limit': rate_limit_info.rate_limit_type,
                'utilization': rate_limit_info.utilization,
                'resets_at': rate_limit_info.resets_at,
            },
        )
        if rate_limit_info.status == _REJECTED:
            raise backend_module.BackendUnavailableError(
                f'The Max subscription {rate_limit_info.rate_limit_type} limit is reached; it resets at {rate_limit_info.resets_at}.'
            )

    def _publish_usage(
        self,
        trigger: trigger_module.Trigger,
        result: claude_agent_sdk.ResultMessage,
    ) -> None:
        """Publishes the turn's token usage.

        total_cost_usd is what the turn would have cost on the API; on the subscription nothing is billed per token.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.
            result (claude_agent_sdk.ResultMessage): Claude Code's summary of the turn.
        """
        usage = result.usage or {}
        self._publish(
            event_module.EventKind.MODEL_USAGE,
            {
                'trigger_id': trigger.trigger_id,
                'backend': self._backend_name,
                'model': self._model,
                'rounds': result.num_turns,
                'prompt_tokens': usage.get('input_tokens', 0),
                'cache_read_tokens': usage.get('cache_read_input_tokens', 0),
                'cache_write_tokens': usage.get(
                    'cache_creation_input_tokens', 0
                ),
                'completion_tokens': usage.get('output_tokens', 0),
                'api_equivalent_cost_usd': result.total_cost_usd,
            },
        )

    def _text_of(self, message: claude_agent_sdk.AssistantMessage) -> str:
        """Joins the text blocks of one assistant message.

        Args:
            message (claude_agent_sdk.AssistantMessage): The message.

        Returns:
            str: Its text, or an empty string when it only called tools or thought.
        """
        parts = []
        for block in message.content:
            if isinstance(block, claude_agent_sdk.TextBlock):
                parts.append(block.text)
        return ''.join(parts)

    def saved_state(self) -> dict[str, Any] | None:
        """Claude Code's session id and the prompt it last saw, so a restart can resume the session.

        Returns:
            dict[str, Any] | None: The session id and prompt fingerprint, or None before the first turn.
        """
        if self.session_id is None:
            return None
        return {
            'session_id': self.session_id,
            'prompt_fingerprint': self._session_prompt_fingerprint,
        }

    async def restore_state(self, state: dict[str, Any]) -> bool:
        """Resumes a session saved before a restart, if Claude Code still has it.

        Claude Code keeps each session as a file named after its id. When that file is gone, resuming would fail, so the runner starts a new session instead and the router tells it what it missed.

        Args:
            state (dict[str, Any]): What saved_state returned before the restart.

        Returns:
            bool: True when the next turn will resume the saved session.
        """
        session_id = state.get('session_id')
        if not isinstance(session_id, str) or not session_id:
            return False
        if not self._session_file_exists(session_id):
            _LOGGER.warning(
                'Claude Code no longer has session %s; desk %s starts a new one',
                session_id,
                self._desk_name,
            )
            return False
        await self._disconnect()
        self.session_id = session_id
        self._session_prompt_fingerprint = state.get('prompt_fingerprint')
        return True

    def _session_file_exists(self, session_id: str) -> bool:
        """Says whether Claude Code still has a session's file.

        Claude Code files sessions under a folder named after the working directory, so every such folder is searched.

        Args:
            session_id (str): The session id.

        Returns:
            bool: True when the file exists.
        """
        directory = self._settings.sessions_directory
        if not directory.is_dir():
            return False
        for _ in directory.glob(f'*/{session_id}.jsonl'):
            return True
        return False

    async def reset(self) -> None:
        """Stops Claude Code and forgets the session, so the next turn starts afresh."""
        await self._disconnect()
        self.session_id = None
        self._session_prompt_fingerprint = None

    async def close(self) -> None:
        """Stops the desk's Claude Code process when the desk stops."""
        await self._disconnect()

    async def _disconnect(self) -> None:
        """Stops Claude Code after a failure, so the next turn starts a fresh process."""
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            await client.disconnect()
        except claude_agent_sdk.ClaudeSDKError:
            _LOGGER.warning('Claude Code did not disconnect cleanly')

    def _log_stderr(self, line: str) -> None:
        """Writes one line of Claude Code's error output to the log.

        Args:
            line (str): The line.
        """
        _LOGGER.debug('claude code: %s', line.rstrip())

    def _publish(self, kind: event_module.EventKind, payload: dict) -> None:
        """Publishes an event from this desk.

        Args:
            kind (event_module.EventKind): What happened.
            payload (dict): The event's details.
        """
        self._event_bus.publish(
            event_module.Event.now(kind, self._desk_name, payload)
        )
