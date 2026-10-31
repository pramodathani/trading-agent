"""Routes for the traders: their state, messages, and pause, resume and flatten.

  GET  /api/traders                     every trader's state, models and session
  GET  /api/traders/{trader}              one trader, with its persona
  GET  /api/traders/{trader}/context      how full the model's context window is, and the trader's tools
  GET  /api/traders/{trader}/commands     the trader's slash commands and usable skills, for a command menu
  POST /api/traders/{trader}/messages     queue a message or /command, with uploads named by id; the reply arrives on /ws/events
  POST /api/traders/{trader}/model        try one backend first, optionally with another of its provider's models, or return to the configured order
  POST /api/traders/{trader}/pause        stop asking models until resumed (commands still work)
  POST /api/traders/{trader}/resume       start answering again
  POST /api/traders/{trader}/flatten      cancel the trader's orders and close its positions

Flatten runs the trader's own flatten_trader tool, so it goes through the risk engine and the journal exactly as when the trader calls it.

Typical usage example:

  application.include_router(TraderRoutes(traders, guard, parts, layout, 'dry_run').router())
"""

from collections.abc import Mapping
from typing import Any, Self

import fastapi
import pydantic

from trading_agent.agent import messages
from trading_agent.attachments import attachment as attachment_module
from trading_agent.attachments import (
    attachment_store as attachment_store_module,
)
from trading_agent.backends import model_router
from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway import gateway_parts
from trading_agent.gateway.routes import route_group
from trading_agent.runtime import trader_runtime
from trading_agent.runtime import trigger as trigger_module
from trading_agent.workspace import workspace_layout

_MOST_ATTACHMENTS = 10


class MessageRequest(pydantic.BaseModel):
    """The body of a message sent to a trader.

    Attributes:
        text: What to tell or ask the trader; may be empty when files are attached.
        attachment_ids: The uploads to send with it, from POST /api/traders/{trader}/attachments.
    """

    text: str = ''
    attachment_ids: list[str] = pydantic.Field(
        default=[], max_length=_MOST_ATTACHMENTS
    )

    @pydantic.model_validator(mode='after')
    def _require_something(self) -> Self:
        """Checks that the message has text or at least one attachment.

        Returns:
            MessageRequest: The message.

        Raises:
            ValueError: The message is empty.
        """
        if not self.text.strip() and not self.attachment_ids:
            raise ValueError('A message needs text or an attached file')
        return self


class ModelRequest(pydantic.BaseModel):
    """The body of a model choice.

    Attributes:
        backend: The backend to try first, or None for the configured order.
        model: Another model of that backend's provider, from its other_models, or None for its configured model.
    """

    backend: str | None = None
    model: str | None = None


class FlattenRequest(pydantic.BaseModel):
    """The body of a flatten request.

    Attributes:
        reason: Why, for the journal.
    """

    reason: str = pydantic.Field(min_length=1)


class TraderRoutes(route_group.RouteGroup):
    """The /api/traders routes."""

    def __init__(
        self,
        traders: Mapping[str, trader_runtime.TraderRuntime],
        guard: access_guard.AccessGuard,
        parts: Mapping[str, gateway_parts.TraderParts] | None = None,
        layout: workspace_layout.WorkspaceLayout | None = None,
        mode: str = 'dry_run',
        attachment_store: attachment_store_module.AttachmentStore | None = None,
        backend_configurations: Mapping[
            str, agent_configuration.BackendConfiguration
        ]
        | None = None,
    ):
        """Creates the routes.

        Args:
            traders (Mapping[str, trader_runtime.TraderRuntime]): The running traders, keyed by name.
            guard (access_guard.AccessGuard): Checks the access token.
            parts (Mapping[str, gateway_parts.TraderParts] | None): Each trader's tools, for flatten, or None when flatten is not offered.
            layout (workspace_layout.WorkspaceLayout | None): Where the personas are, or None to leave them out.
            mode (str): "dry_run" or "live", reported with each trader.
            attachment_store (attachment_store_module.AttachmentStore | None): Where uploads are kept, or None when messages cannot carry files.
            backend_configurations (Mapping[str, agent_configuration.BackendConfiguration] | None): Each backend's settings, keyed by name, for the model menu, or None to leave them out.
        """
        super().__init__(guard)
        self._traders = traders
        self._parts = parts or {}
        self._layout = layout
        self._mode = mode
        self._attachment_store = attachment_store
        self._backend_configurations = backend_configurations or {}

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the trader routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route('/api/traders', self.list_traders, methods=['GET'])
        router.add_api_route(
            '/api/traders/{trader_name}', self.trader, methods=['GET']
        )
        router.add_api_route(
            '/api/traders/{trader_name}/context', self.context, methods=['GET']
        )
        router.add_api_route(
            '/api/traders/{trader_name}/commands',
            self.commands,
            methods=['GET'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/messages',
            self.send_message,
            methods=['POST'],
            status_code=202,
        )
        router.add_api_route(
            '/api/traders/{trader_name}/model',
            self.choose_model,
            methods=['POST'],
        )
        router.add_api_route(
            '/api/traders/{trader_name}/pause', self.pause, methods=['POST']
        )
        router.add_api_route(
            '/api/traders/{trader_name}/resume', self.resume, methods=['POST']
        )
        router.add_api_route(
            '/api/traders/{trader_name}/flatten', self.flatten, methods=['POST']
        )

    def list_traders(self) -> dict[str, Any]:
        """Every trader's state.

        Returns:
            dict[str, Any]: The traders, in configuration order, and the mode.
        """
        traders = []
        for trader in self._traders.values():
            traders.append(self._summary(trader))
        return {
            'mode': self._mode,
            'traders': traders,
        }

    def trader(self, trader_name: str) -> dict[str, Any]:
        """One trader's state and persona.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: The trader's state, models, session and Persona.md text.
        """
        trader = self._find(self._traders, trader_name, 'trader')
        summary = self._summary(trader)
        summary['persona'] = None
        if self._layout is not None:
            persona = self._layout.persona_file(trader_name)
            if persona.is_file():
                summary['persona'] = persona.read_text(encoding='utf-8')
        return summary

    def context(self, trader_name: str) -> dict[str, Any]:
        """How full the trader's context window is, and which tools it has.

        The snapshot belongs to the backend that answered last. Claude's is measured by Claude Code at the end of each turn; the other backends' are estimated from their conversation when asked.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: The trader's name, the snapshot or None when there is none yet, and its tool names.
        """
        trader = self._find(self._traders, trader_name, 'trader')
        usage = trader.turn_runner.context_usage()
        tools = []
        trader_parts = self._parts.get(trader_name)
        if trader_parts is not None:
            tools = trader_parts.tools.tool_names
        return {
            'trader': trader_name,
            'usage': None if usage is None else usage.to_payload(),
            'tools': tools,
        }

    def commands(self, trader_name: str) -> dict[str, Any]:
        """The trader's slash commands and usable skills.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: The trader's name and its entries, each with name, usage, description, kind and runs.
        """
        trader = self._find(self._traders, trader_name, 'trader')
        return {
            'trader': trader_name,
            'commands': trader.command_catalogue(),
        }

    def send_message(
        self,
        trader_name: str,
        message: MessageRequest,
    ) -> dict[str, Any]:
        """Queues a message for a trader and returns at once.

        Args:
            trader_name (str): The trader.
            message (MessageRequest): The message.

        Returns:
            dict[str, Any]: The new trigger's identifier, to match it with later events.

        Raises:
            fastapi.HTTPException: There is no such trader (404), or an attachment is not one of the trader's uploads (422).
        """
        trader = self._find(self._traders, trader_name, 'trader')
        trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.USER_MESSAGE,
            trader_name,
            message.text.strip(),
            self._attachments(trader_name, message.attachment_ids),
        )
        trader.submit(trigger)
        return {
            'trigger_id': trigger.trigger_id,
        }

    def _attachments(
        self,
        trader_name: str,
        attachment_ids: list[str],
    ) -> tuple[attachment_module.Attachment, ...]:
        """Looks up the uploads a message names.

        Args:
            trader_name (str): The trader the uploads must belong to.
            attachment_ids (list[str]): Their identifiers.

        Returns:
            tuple[attachment_module.Attachment, ...]: The attachments, in the order named.

        Raises:
            fastapi.HTTPException: Files are named but none can be attached here, or one is not the trader's upload (422).
        """
        if not attachment_ids:
            return ()
        if self._attachment_store is None:
            raise fastapi.HTTPException(
                status_code=422,
                detail='This gateway takes no attached files',
            )
        found = []
        for attachment_id in attachment_ids:
            try:
                found.append(
                    self._attachment_store.find(trader_name, attachment_id)
                )
            except attachment_store_module.AttachmentNotFoundError as error:
                raise fastapi.HTTPException(
                    status_code=422, detail=str(error)
                ) from error
        return tuple(found)

    def choose_model(
        self,
        trader_name: str,
        request: ModelRequest,
    ) -> dict[str, Any]:
        """Tries one backend first from now on, optionally with another of its provider's models, or returns to the configured order, as /model does.

        Args:
            trader_name (str): The trader.
            request (ModelRequest): The backend to try first and its model, or None for both.

        Returns:
            dict[str, Any]: The trader's state afterwards.

        Raises:
            fastapi.HTTPException: The trader has no models (status 409), or no backend of that name, or the backend does not offer that model (status 400).
        """
        trader = self._find(self._traders, trader_name, 'trader')
        router = trader.turn_runner
        if not isinstance(router, model_router.ModelRouter):
            raise fastapi.HTTPException(
                status_code=409, detail='This trader has no models connected'
            )
        if request.model is not None and request.backend is not None:
            configuration = self._backend_configurations.get(request.backend)
            offered = []
            if configuration is not None:
                offered = [
                    configuration.model,
                    *configuration.other_models,
                ]
            if request.model not in offered:
                raise fastapi.HTTPException(
                    status_code=400,
                    detail=f'Backend {request.backend!r} does not offer the model {request.model!r}; add it to other_models in trading_agent.toml',
                )
        try:
            router.choose(request.backend, request.model)
        except ValueError as error:
            raise fastapi.HTTPException(
                status_code=400, detail=str(error)
            ) from error
        return self._summary(trader)

    def pause(self, trader_name: str) -> dict[str, Any]:
        """Pauses a trader.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: The trader's state.
        """
        trader = self._find(self._traders, trader_name, 'trader')
        trader.paused = True
        return self._summary(trader)

    def resume(self, trader_name: str) -> dict[str, Any]:
        """Resumes a trader.

        Args:
            trader_name (str): The trader.

        Returns:
            dict[str, Any]: The trader's state.
        """
        trader = self._find(self._traders, trader_name, 'trader')
        trader.paused = False
        return self._summary(trader)

    async def flatten(
        self,
        trader_name: str,
        request: FlattenRequest,
    ) -> dict[str, Any]:
        """Cancels a trader's orders and closes its positions, through its own flatten_trader tool.

        Args:
            trader_name (str): The trader.
            request (FlattenRequest): Why.

        Returns:
            dict[str, Any]: The tool's report and whether it failed.
        """
        parts = self._find(self._parts, trader_name, 'trader')
        result = await parts.tools.run(
            messages.ToolCall.new(
                'flatten_trader',
                {
                    'reason': f'From the user, through the API: {request.reason}',
                },
            )
        )
        return {
            'text': result.text,
            'is_error': result.is_error,
        }

    def _summary(self, trader: trader_runtime.TraderRuntime) -> dict[str, Any]:
        """Describes a trader's state.

        Args:
            trader (trader_runtime.TraderRuntime): The trader.

        Returns:
            dict[str, Any]: Its name, state, queue, pause, models and session.
        """
        summary = {
            'name': trader.name,
            'state': str(trader.state),
            'paused': trader.paused,
            'queued': trader.queued_count,
            'mode': self._mode,
            'models': [],
            'preferred_model': None,
            'last_model': None,
            'session_id': None,
            'exchanges': 0,
            'backends': [],
        }
        router = trader.turn_runner
        if isinstance(router, model_router.ModelRouter):
            summary['models'] = router.status_lines()
            summary['preferred_model'] = router.preferred_backend_name
            summary['last_model'] = router.last_backend_name
            summary['session_id'] = router.session_id
            summary['exchanges'] = len(router.exchanges)
            active = router.active_models()
            backends = []
            for backend_name in router.backend_names:
                configuration = self._backend_configurations.get(backend_name)
                entry = {
                    'name': backend_name,
                    'kind': '',
                    'model': '',
                    'active_model': active.get(backend_name),
                    'other_models': [],
                }
                if configuration is not None:
                    entry['kind'] = configuration.kind
                    entry['model'] = configuration.model
                    entry['other_models'] = list(configuration.other_models)
                backends.append(entry)
            summary['backends'] = backends
        return summary
