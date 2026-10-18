"""Routes for the desks' questions, plans and permission requests to the user.

  GET  /api/requests                     the requests, pending ones only unless status=all
  POST /api/requests/{id}/answer         answer a question request
  POST /api/requests/{id}/plan           approve a plan, or ask for changes
  POST /api/requests/{id}/permission     allow a held call once or always, or deny it
  POST /api/requests/{id}/dismiss        close a request without answering
  GET  /api/permissions                  the standing "Always allow" permissions
  POST /api/permissions/revoke           make a desk ask again before using a tool

Each response is handed to the desk as a new message; the desk never waited for it. A response is recorded as given "via web" unless the client names itself with the header X-Trading-Agent-Client: terminal.

Typical usage example:

  application.include_router(RequestRoutes(guard, store, responder).router())
"""

from collections.abc import Callable
from typing import Any

import fastapi
import pydantic

from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import route_group
from trading_agent.requests import permission_grants as permission_grants_module
from trading_agent.requests import user_request as user_request_module
from trading_agent.requests import user_request_responder as user_request_responder_module
from trading_agent.requests import user_request_store as user_request_store_module

_WEB = 'web'
_CLIENTS = (
    'web',
    'terminal',
)
_CLIENT_HEADER = fastapi.Header(default=_WEB, alias='X-Trading-Agent-Client')


class QuestionAnswer(pydantic.BaseModel):
    """The answer to one question.

    Attributes:
        selected: The labels of the options chosen.
        other: The user's own answer typed under "Other", or empty.
    """

    selected: list[str] = []
    other: str = pydantic.Field(default='', max_length=2000)


class AnswerRequest(pydantic.BaseModel):
    """The body of an answer to a question request.

    Attributes:
        answers: One answer per question, in order.
    """

    answers: list[QuestionAnswer] = pydantic.Field(min_length=1, max_length=4)


class PlanDecisionRequest(pydantic.BaseModel):
    """The body of a decision on a plan.

    Attributes:
        decision: "approve" or "revise".
        feedback: What should change, or a note with an approval.
    """

    decision: str
    feedback: str = pydantic.Field(default='', max_length=4000)


class PermissionDecisionRequest(pydantic.BaseModel):
    """The body of a decision on a held call.

    Attributes:
        decision: "allow_once", "always_allow" or "deny".
        reason: Why it was denied, or a note; may be empty.
    """

    decision: str
    reason: str = pydantic.Field(default='', max_length=2000)


class RevokeRequest(pydantic.BaseModel):
    """The body of a revocation.

    Attributes:
        desk: The desk.
        tool_name: The tool it must ask about again.
    """

    desk: str
    tool_name: str


class RequestRoutes(route_group.RouteGroup):
    """The /api/requests routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        store: user_request_store_module.UserRequestStore,
        responder: user_request_responder_module.UserRequestResponder,
        grants: permission_grants_module.PermissionGrants | None = None,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            store (user_request_store_module.UserRequestStore): Where the requests are kept.
            responder (user_request_responder_module.UserRequestResponder): Records responses and tells the desks.
            grants (permission_grants_module.PermissionGrants | None): The standing permissions, or None when permissions are not used.
        """
        super().__init__(guard)
        self._store = store
        self._responder = responder
        self._grants = grants

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the request routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route('/api/requests', self.list_requests, methods=['GET'])
        router.add_api_route(
            '/api/requests/{request_id}/answer', self.answer, methods=['POST']
        )
        router.add_api_route(
            '/api/requests/{request_id}/plan', self.decide_plan, methods=['POST']
        )
        router.add_api_route(
            '/api/requests/{request_id}/permission',
            self.decide_permission,
            methods=['POST'],
        )
        router.add_api_route(
            '/api/requests/{request_id}/dismiss', self.dismiss, methods=['POST']
        )
        router.add_api_route(
            '/api/permissions', self.list_permissions, methods=['GET']
        )
        router.add_api_route(
            '/api/permissions/revoke', self.revoke_permission, methods=['POST']
        )

    def list_requests(self, status: str = 'pending') -> dict[str, Any]:
        """Lists the requests.

        Args:
            status (str): "pending" for those still waiting, or "all".

        Returns:
            dict[str, Any]: The requests, oldest first.
        """
        if status == 'all':
            found = self._store.all()
        else:
            found = self._store.pending()
        requests = []
        for request in found:
            requests.append(request.to_json_dictionary())
        return {
            'requests': requests,
        }

    def answer(
        self,
        request_id: str,
        body: AnswerRequest,
        client: str = _CLIENT_HEADER,
    ) -> dict[str, Any]:
        """Answers a question request.

        Args:
            request_id (str): The request.
            body (AnswerRequest): The answers.
            client (str): The client that sent it, from the X-Trading-Agent-Client header.

        Returns:
            dict[str, Any]: The answered request.

        Raises:
            fastapi.HTTPException: No such request (404), it is no longer pending (409), or the answers do not fit it (422).
        """
        answers = []
        for answer in body.answers:
            answers.append(answer.model_dump())
        return self._respond(
            request_id,
            lambda: self._responder.answer_question(
                request_id, answers, self._via(client)
            ),
        )

    def decide_plan(
        self,
        request_id: str,
        body: PlanDecisionRequest,
        client: str = _CLIENT_HEADER,
    ) -> dict[str, Any]:
        """Approves a plan or asks for changes.

        Args:
            request_id (str): The request.
            body (PlanDecisionRequest): The decision and feedback.
            client (str): The client that sent it, from the X-Trading-Agent-Client header.

        Returns:
            dict[str, Any]: The decided request.

        Raises:
            fastapi.HTTPException: No such request (404), it is no longer pending (409), or the decision is not valid (422).
        """
        return self._respond(
            request_id,
            lambda: self._responder.decide_plan(
                request_id,
                body.decision,
                body.feedback,
                self._via(client),
            ),
        )

    async def decide_permission(
        self,
        request_id: str,
        body: PermissionDecisionRequest,
        client: str = _CLIENT_HEADER,
    ) -> dict[str, Any]:
        """Allows a held call once or always, running it, or denies it.

        Args:
            request_id (str): The request.
            body (PermissionDecisionRequest): The decision and reason.
            client (str): The client that sent it, from the X-Trading-Agent-Client header.

        Returns:
            dict[str, Any]: The decided request, with the call's result when it ran.

        Raises:
            fastapi.HTTPException: No such request (404), it is no longer pending or has lapsed (409), or the decision is not valid (422).
        """
        try:
            self._store.get(request_id)
        except user_request_store_module.UserRequestError as error:
            raise fastapi.HTTPException(status_code=404, detail=str(error)) from error
        try:
            request = await self._responder.decide_permission(
                request_id,
                body.decision,
                body.reason,
                self._via(client),
            )
        except user_request_store_module.UserRequestError as error:
            raise fastapi.HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise fastapi.HTTPException(status_code=422, detail=str(error)) from error
        return request.to_json_dictionary()

    def list_permissions(self) -> dict[str, Any]:
        """Lists the standing permissions.

        Returns:
            dict[str, Any]: The grants, oldest first.
        """
        grants = []
        if self._grants is not None:
            for grant in self._grants.all():
                grants.append(
                    {
                        'desk': grant.desk,
                        'tool_name': grant.tool_name,
                        'granted_at': grant.granted_at,
                    }
                )
        return {
            'grants': grants,
        }

    def revoke_permission(self, body: RevokeRequest) -> dict[str, Any]:
        """Makes a desk ask again before using a tool.

        Args:
            body (RevokeRequest): The desk and the tool.

        Returns:
            dict[str, Any]: Whether a grant was removed.

        Raises:
            fastapi.HTTPException: There is no such grant (404).
        """
        if self._grants is None or not self._grants.revoke(body.desk, body.tool_name):
            raise fastapi.HTTPException(
                status_code=404,
                detail=f'No standing permission for {body.tool_name!r} on desk {body.desk!r}',
            )
        return {
            'revoked': True,
        }

    def dismiss(
        self,
        request_id: str,
        client: str = _CLIENT_HEADER,
    ) -> dict[str, Any]:
        """Closes a request without answering it.

        Args:
            request_id (str): The request.
            client (str): The client that sent it, from the X-Trading-Agent-Client header.

        Returns:
            dict[str, Any]: The dismissed request.

        Raises:
            fastapi.HTTPException: No such request (404), or it is no longer pending (409).
        """
        return self._respond(
            request_id,
            lambda: self._responder.dismiss(request_id, self._via(client)),
        )

    def _via(self, client: str) -> str:
        """The channel a response is recorded as coming through.

        Args:
            client (str): The X-Trading-Agent-Client header's value.

        Returns:
            str: "terminal" for the terminal program, otherwise "web".
        """
        if client in _CLIENTS:
            return client
        return _WEB

    def _respond(
        self,
        request_id: str,
        action: Callable[[], user_request_module.UserRequest],
    ) -> dict[str, Any]:
        """Runs a response, turning its failures into HTTP errors.

        Args:
            request_id (str): The request.
            action (Callable[[], user_request_module.UserRequest]): The response to run.

        Returns:
            dict[str, Any]: The request afterwards.

        Raises:
            fastapi.HTTPException: No such request (404), it is no longer pending (409), or the response does not fit it (422).
        """
        try:
            self._store.get(request_id)
        except user_request_store_module.UserRequestError as error:
            raise fastapi.HTTPException(status_code=404, detail=str(error)) from error
        try:
            request = action()
        except user_request_store_module.UserRequestError as error:
            raise fastapi.HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise fastapi.HTTPException(status_code=422, detail=str(error)) from error
        return request.to_json_dictionary()
