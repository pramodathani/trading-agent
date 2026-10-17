"""Routes for the desks: their state, messages, and pause, resume and flatten.

  GET  /api/desks                     every desk's state, models and session
  GET  /api/desks/{desk}              one desk, with its persona
  GET  /api/desks/{desk}/context      how full the model's context window is, and the desk's tools
  POST /api/desks/{desk}/messages     queue a message or /command, with uploads named by id; the reply arrives on /ws/events
  POST /api/desks/{desk}/model        try one backend first, optionally with another of its provider's models, or return to the configured order
  POST /api/desks/{desk}/pause        stop asking models until resumed (commands still work)
  POST /api/desks/{desk}/resume       start answering again
  POST /api/desks/{desk}/flatten      cancel the desk's orders and close its positions

Flatten runs the desk's own flatten_desk tool, so it goes through the risk engine and the journal exactly as when the desk calls it.

Typical usage example:

  application.include_router(DeskRoutes(desks, guard, parts, layout, 'dry_run').router())
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
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import trigger as trigger_module
from trading_agent.workspace import workspace_layout

_MOST_ATTACHMENTS = 10


class MessageRequest(pydantic.BaseModel):
    """The body of a message sent to a desk.

    Attributes:
        text: What to tell or ask the desk; may be empty when files are attached.
        attachment_ids: The uploads to send with it, from POST /api/desks/{desk}/attachments.
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


class DeskRoutes(route_group.RouteGroup):
    """The /api/desks routes."""

    def __init__(
        self,
        desks: Mapping[str, desk_runtime.DeskRuntime],
        guard: access_guard.AccessGuard,
        parts: Mapping[str, gateway_parts.DeskParts] | None = None,
        layout: workspace_layout.WorkspaceLayout | None = None,
        mode: str = 'dry_run',
        attachment_store: attachment_store_module.AttachmentStore | None = None,
        backend_configurations: Mapping[str, agent_configuration.BackendConfiguration] | None = None,
    ):
        """Creates the routes.

        Args:
            desks (Mapping[str, desk_runtime.DeskRuntime]): The running desks, keyed by name.
            guard (access_guard.AccessGuard): Checks the access token.
            parts (Mapping[str, gateway_parts.DeskParts] | None): Each desk's tools, for flatten, or None when flatten is not offered.
            layout (workspace_layout.WorkspaceLayout | None): Where the personas are, or None to leave them out.
            mode (str): "dry_run" or "live", reported with each desk.
            attachment_store (attachment_store_module.AttachmentStore | None): Where uploads are kept, or None when messages cannot carry files.
            backend_configurations (Mapping[str, agent_configuration.BackendConfiguration] | None): Each backend's settings, keyed by name, for the model menu, or None to leave them out.
        """
        super().__init__(guard)
        self._desks = desks
        self._parts = parts or {}
        self._layout = layout
        self._mode = mode
        self._attachment_store = attachment_store
        self._backend_configurations = backend_configurations or {}

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the desk routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route('/api/desks', self.list_desks, methods=['GET'])
        router.add_api_route(
            '/api/desks/{desk_name}', self.desk, methods=['GET']
        )
        router.add_api_route(
            '/api/desks/{desk_name}/context', self.context, methods=['GET']
        )
        router.add_api_route(
            '/api/desks/{desk_name}/messages',
            self.send_message,
            methods=['POST'],
            status_code=202,
        )
        router.add_api_route(
            '/api/desks/{desk_name}/model', self.choose_model, methods=['POST']
        )
        router.add_api_route(
            '/api/desks/{desk_name}/pause', self.pause, methods=['POST']
        )
        router.add_api_route(
            '/api/desks/{desk_name}/resume', self.resume, methods=['POST']
        )
        router.add_api_route(
            '/api/desks/{desk_name}/flatten', self.flatten, methods=['POST']
        )

    def list_desks(self) -> dict[str, Any]:
        """Every desk's state.

        Returns:
            dict[str, Any]: The desks, in configuration order, and the mode.
        """
        desks = []
        for desk in self._desks.values():
            desks.append(self._summary(desk))
        return {
            'mode': self._mode,
            'desks': desks,
        }

    def desk(self, desk_name: str) -> dict[str, Any]:
        """One desk's state and persona.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The desk's state, models, session and Persona.md text.
        """
        desk = self._find(self._desks, desk_name, 'desk')
        summary = self._summary(desk)
        summary['persona'] = None
        if self._layout is not None:
            persona = self._layout.persona_file(desk_name)
            if persona.is_file():
                summary['persona'] = persona.read_text(encoding='utf-8')
        return summary

    def context(self, desk_name: str) -> dict[str, Any]:
        """How full the desk's context window is, and which tools it has.

        The snapshot belongs to the backend that answered last. Claude's is measured by Claude Code at the end of each turn; the other backends' are estimated from their conversation when asked.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The desk's name, the snapshot or None when there is none yet, and its tool names.
        """
        desk = self._find(self._desks, desk_name, 'desk')
        usage = desk.turn_runner.context_usage()
        tools = []
        desk_parts = self._parts.get(desk_name)
        if desk_parts is not None:
            tools = desk_parts.tools.tool_names
        return {
            'desk': desk_name,
            'usage': None if usage is None else usage.to_payload(),
            'tools': tools,
        }

    def send_message(
        self,
        desk_name: str,
        message: MessageRequest,
    ) -> dict[str, Any]:
        """Queues a message for a desk and returns at once.

        Args:
            desk_name (str): The desk.
            message (MessageRequest): The message.

        Returns:
            dict[str, Any]: The new trigger's identifier, to match it with later events.

        Raises:
            fastapi.HTTPException: There is no such desk (404), or an attachment is not one of the desk's uploads (422).
        """
        desk = self._find(self._desks, desk_name, 'desk')
        trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.USER_MESSAGE,
            desk_name,
            message.text.strip(),
            self._attachments(desk_name, message.attachment_ids),
        )
        desk.submit(trigger)
        return {
            'trigger_id': trigger.trigger_id,
        }

    def _attachments(
        self,
        desk_name: str,
        attachment_ids: list[str],
    ) -> tuple[attachment_module.Attachment, ...]:
        """Looks up the uploads a message names.

        Args:
            desk_name (str): The desk the uploads must belong to.
            attachment_ids (list[str]): Their identifiers.

        Returns:
            tuple[attachment_module.Attachment, ...]: The attachments, in the order named.

        Raises:
            fastapi.HTTPException: Files are named but none can be attached here, or one is not the desk's upload (422).
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
                    self._attachment_store.find(desk_name, attachment_id)
                )
            except attachment_store_module.AttachmentNotFoundError as error:
                raise fastapi.HTTPException(
                    status_code=422, detail=str(error)
                ) from error
        return tuple(found)

    def choose_model(
        self,
        desk_name: str,
        request: ModelRequest,
    ) -> dict[str, Any]:
        """Tries one backend first from now on, optionally with another of its provider's models, or returns to the configured order, as /model does.

        Args:
            desk_name (str): The desk.
            request (ModelRequest): The backend to try first and its model, or None for both.

        Returns:
            dict[str, Any]: The desk's state afterwards.

        Raises:
            fastapi.HTTPException: The desk has no models (status 409), or no backend of that name, or the backend does not offer that model (status 400).
        """
        desk = self._find(self._desks, desk_name, 'desk')
        router = desk.turn_runner
        if not isinstance(router, model_router.ModelRouter):
            raise fastapi.HTTPException(
                status_code=409, detail='This desk has no models connected'
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
        return self._summary(desk)

    def pause(self, desk_name: str) -> dict[str, Any]:
        """Pauses a desk.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The desk's state.
        """
        desk = self._find(self._desks, desk_name, 'desk')
        desk.paused = True
        return self._summary(desk)

    def resume(self, desk_name: str) -> dict[str, Any]:
        """Resumes a desk.

        Args:
            desk_name (str): The desk.

        Returns:
            dict[str, Any]: The desk's state.
        """
        desk = self._find(self._desks, desk_name, 'desk')
        desk.paused = False
        return self._summary(desk)

    async def flatten(
        self,
        desk_name: str,
        request: FlattenRequest,
    ) -> dict[str, Any]:
        """Cancels a desk's orders and closes its positions, through its own flatten_desk tool.

        Args:
            desk_name (str): The desk.
            request (FlattenRequest): Why.

        Returns:
            dict[str, Any]: The tool's report and whether it failed.
        """
        parts = self._find(self._parts, desk_name, 'desk')
        result = await parts.tools.run(
            messages.ToolCall.new(
                'flatten_desk',
                {
                    'reason': f'From the user, through the API: {request.reason}',
                },
            )
        )
        return {
            'text': result.text,
            'is_error': result.is_error,
        }

    def _summary(self, desk: desk_runtime.DeskRuntime) -> dict[str, Any]:
        """Describes a desk's state.

        Args:
            desk (desk_runtime.DeskRuntime): The desk.

        Returns:
            dict[str, Any]: Its name, state, queue, pause, models and session.
        """
        summary = {
            'name': desk.name,
            'state': str(desk.state),
            'paused': desk.paused,
            'queued': desk.queued_count,
            'mode': self._mode,
            'models': [],
            'preferred_model': None,
            'last_model': None,
            'session_id': None,
            'exchanges': 0,
            'backends': [],
        }
        router = desk.turn_runner
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
