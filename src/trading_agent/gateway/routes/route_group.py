"""The shared base of the gateway's API route groups.

Every route of a group needs the access token, so the group builds its router with the guard's check attached, and each subclass only adds its own routes.

Typical usage example:

  class AccountRoutes(RouteGroup):
      def _add_routes(self, router):
          router.add_api_route('/api/account', self.account, methods=['GET'])
"""

from collections.abc import Mapping
from typing import TypeVar

import fastapi

from trading_agent.gateway import access_guard

_Part = TypeVar('_Part')


class RouteGroup:
    """A set of related API routes behind the access token."""

    def __init__(self, guard: access_guard.AccessGuard):
        """Creates the group.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
        """
        self._guard = guard

    def router(self) -> fastapi.APIRouter:
        """Builds the router, every route requiring the token.

        Returns:
            fastapi.APIRouter: The router.
        """
        router = fastapi.APIRouter(
            dependencies=[
                fastapi.Depends(self._guard.require_http_token),
            ],
        )
        self._add_routes(router)
        return router

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the group's routes.

        Args:
            router (fastapi.APIRouter): The router to add them to.

        Raises:
            NotImplementedError: Always, because subclasses must override this method.
        """
        raise NotImplementedError

    def _find(self, parts: Mapping[str, _Part], name: str, kind: str) -> _Part:
        """Looks a desk's part up by name, or answers 404.

        Args:
            parts (Mapping[str, _Part]): The parts, keyed by name.
            name (str): The name asked for.
            kind (str): What is looked up, such as "desk", for the message.

        Returns:
            _Part: The part.

        Raises:
            fastapi.HTTPException: There is none of that name (status 404).
        """
        part = parts.get(name)
        if part is None:
            raise fastapi.HTTPException(
                status_code=404, detail=f'No {kind} named {name!r}'
            )
        return part
