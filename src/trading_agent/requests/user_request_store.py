"""Saves the traders' requests to the user, one JSON file each in the trader's requests folder.

Typical usage example:

  store = UserRequestStore(layout)
  store.save(request)
  store.pending()
"""

import dataclasses
import datetime
import json

from trading_agent.requests import user_request as user_request_module
from trading_agent.workspace import workspace_layout


class UserRequestError(ValueError):
    """A request does not exist, or is no longer waiting for a response."""


class UserRequestStore:
    """Saves, finds and lists requests, and marks lapsed ones as expired."""

    def __init__(self, layout: workspace_layout.WorkspaceLayout):
        """Creates the store.

        Args:
            layout (workspace_layout.WorkspaceLayout): The workspace whose traders' requests folders hold the requests.
        """
        self._layout = layout

    def save(self, request: user_request_module.UserRequest) -> None:
        """Writes a request, replacing any earlier version of it.

        Args:
            request (user_request_module.UserRequest): The request.
        """
        directory = self._layout.requests_directory(request.trader)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{request.request_id}.json'
        path.write_text(
            json.dumps(request.to_json_dictionary(), indent=2),
            encoding='utf-8',
        )

    def all(self) -> list[user_request_module.UserRequest]:
        """Every request from every trader, oldest first, with lapsed ones shown as expired.

        A lapsed request is only shown as expired here; expire_lapsed saves the change, so that the trader is told exactly once.

        Returns:
            list[user_request_module.UserRequest]: The requests.
        """
        now = datetime.datetime.now(datetime.UTC)
        requests = []
        for request in self._saved():
            if (
                request.status == user_request_module.PENDING
                and request.is_expired(now)
            ):
                request = dataclasses.replace(
                    request,
                    status=user_request_module.EXPIRED,
                )
            requests.append(request)
        return requests

    def expire_lapsed(self) -> list[user_request_module.UserRequest]:
        """Saves every lapsed pending request as expired.

        Returns:
            list[user_request_module.UserRequest]: The requests that have just expired.
        """
        now = datetime.datetime.now(datetime.UTC)
        expired = []
        for request in self._saved():
            if (
                request.status == user_request_module.PENDING
                and request.is_expired(now)
            ):
                lapsed = dataclasses.replace(
                    request,
                    status=user_request_module.EXPIRED,
                )
                self.save(lapsed)
                expired.append(lapsed)
        return expired

    def pending(self) -> list[user_request_module.UserRequest]:
        """The requests still waiting for a response, oldest first.

        Returns:
            list[user_request_module.UserRequest]: The pending requests.
        """
        waiting = []
        for request in self.all():
            if request.status == user_request_module.PENDING:
                waiting.append(request)
        return waiting

    def get(self, request_id: str) -> user_request_module.UserRequest:
        """Finds one request.

        Args:
            request_id (str): Its identifier.

        Returns:
            user_request_module.UserRequest: The request.

        Raises:
            UserRequestError: No request has that identifier.
        """
        for request in self.all():
            if request.request_id == request_id:
                return request
        raise UserRequestError(f'No request with id {request_id!r}')

    def pending_request(
        self, request_id: str
    ) -> user_request_module.UserRequest:
        """Finds a request that is still waiting for a response.

        Args:
            request_id (str): Its identifier.

        Returns:
            user_request_module.UserRequest: The request.

        Raises:
            UserRequestError: It does not exist, or was already answered, dismissed or expired.
        """
        request = self.get(request_id)
        if request.status != user_request_module.PENDING:
            raise UserRequestError(
                f'Request {request_id} is already {request.status}'
            )
        return request

    def _saved(self) -> list[user_request_module.UserRequest]:
        """Every request as saved, oldest first.

        Returns:
            list[user_request_module.UserRequest]: The requests.
        """
        requests = []
        for path in sorted(self._layout.root.glob('traders/*/requests/*.json')):
            dictionary = json.loads(path.read_text(encoding='utf-8'))
            requests.append(
                user_request_module.UserRequest.from_json_dictionary(dictionary)
            )
        requests.sort(key=self._created_at)
        return requests

    @staticmethod
    def _created_at(request: user_request_module.UserRequest) -> str:
        """The sort key for oldest first.

        Args:
            request (user_request_module.UserRequest): A request.

        Returns:
            str: Its creation time as ISO text, which sorts in time order.
        """
        return request.created_at
