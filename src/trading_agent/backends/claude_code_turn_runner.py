"""Runs a desk's turns on Claude through Claude Code and the Max subscription.

Claude Code runs the agent loop itself, so this is a turn runner rather than a ModelBackend. It keeps one Claude Code session per desk, so Claude remembers earlier turns. It is set up so that it never stops for a human:

- permission_mode is bypassPermissions and setting_sources is empty, so no "ask" rule from any settings file applies;
- the subscription token from `claude setup-token` is passed as CLAUDE_CODE_OAUTH_TOKEN;
- every built-in Claude Code tool is switched off, and a PreToolUse hook allows only trading-agent's tools.

Typical usage example:

  runner = ClaudeCodeTurnRunner('main', 'claude', backend_configuration, bridge, event_bus, settings)
  result = await runner.run_turn(trigger)
"""

import dataclasses
import logging
import os
from pathlib import Path
from typing import Any

import claude_agent_sdk

from trading_agent.agent import prompt_builder as prompt_builder_module
from trading_agent.backends import backend as backend_module
from trading_agent.backends import claude_tool_allowlist_hook
from trading_agent.backends import claude_tool_bridge
from trading_agent.configuration import agent_configuration
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner

_LOGGER = logging.getLogger(__name__)
_API_KEY_VARIABLE = 'ANTHROPIC_API_KEY'
_REJECTED = 'rejected'


@dataclasses.dataclass(frozen=True)
class ClaudeCodeSettings:
    """The settings of one Claude Code session that do not come from the backend's table.

    Attributes:
        prompt_builder: Builds the desk's instructions before every turn.
        oauth_token: The subscription token from `claude setup-token`.
        working_directory: The folder Claude Code runs in.
        maximum_rounds: The most model calls one turn may make.
    """

    prompt_builder: prompt_builder_module.PromptBuilder
    oauth_token: str
    working_directory: Path
    maximum_rounds: int


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
    ):
        """Creates the runner without starting Claude Code.

        Args:
            desk_name (str): The desk the session belongs to.
            backend_name (str): The backend's name in trading_agent.toml.
            backend_configuration (agent_configuration.BackendConfiguration): Its settings, of kind "claude_code".
            bridge (claude_tool_bridge.ClaudeToolBridge): The desk's tools, as Claude Code sees them.
            event_bus (event_bus_module.EventBus): Where every step is published.
            settings (ClaudeCodeSettings): The prompt, token, folder and round limit.
        """
        self._desk_name = desk_name
        self._backend_name = backend_name
        self._model = backend_configuration.model
        self._bridge = bridge
        self._event_bus = event_bus
        self._settings = settings
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
            await client.query(self._query_text(prompt, trigger))
            self._session_prompt_fingerprint = prompt.fingerprint
            return await self._read_response(client, trigger)
        except backend_module.BackendUnavailableError:
            await self._disconnect()
            raise
        except claude_agent_sdk.ClaudeSDKError as error:
            await self._disconnect()
            raise backend_module.BackendUnavailableError(
                f'Claude Code failed: {error!r}'
            ) from error

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

        A resumed Claude Code session keeps the system prompt it started with and ignores a new one, so changed workspace files are delivered inside the message instead. Once sent, they are part of the session and survive a later resume.

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
                '[Your instruction files have changed since this session started. The complete current versions follow. They replace the versions in your system prompt and in any earlier update; follow these from now on.]',
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
            },
            permission_mode='bypassPermissions',
            setting_sources=[],
            include_partial_messages=True,
            max_turns=self._settings.maximum_rounds,
            cwd=self._settings.working_directory,
            env={
                'CLAUDE_CODE_OAUTH_TOKEN': self._settings.oauth_token,
            },
            resume=self.session_id,
            stderr=self._log_stderr,
        )

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
