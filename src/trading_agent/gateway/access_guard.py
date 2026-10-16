"""Checks that a request to the gateway carries the access token.

HTTP requests send the token as `Authorization: Bearer <token>`. Browsers cannot set headers on a WebSocket, so a WebSocket sends it as the `token` query parameter instead.

Typical usage example:

  guard = AccessGuard(secrets.gateway_access_token)
  router = fastapi.APIRouter(dependencies=[fastapi.Depends(guard.require_http_token)])
"""

import hmac

import fastapi

_BEARER_PREFIX = 'Bearer '


class AccessGuard:
    """Compares the token a client presents with the configured one."""

    def __init__(self, access_token: str):
        """Creates a guard for one token.

        Args:
            access_token (str): The token every request must present.

        Raises:
            ValueError: The token is empty, which would let anyone in.
        """
        if not access_token:
            raise ValueError(
                'TRADING_AGENT_GATEWAY_ACCESS_TOKEN is empty; set it in .env'
            )
        self._access_token = access_token

    def is_valid(self, presented_token: str | None) -> bool:
        """Checks a presented token in constant time.

        Args:
            presented_token (str | None): The token the client sent, or None if it sent none.

        Returns:
            bool: True if the token matches.
        """
        if presented_token is None:
            return False
        return hmac.compare_digest(
            presented_token.encode('utf-8'),
            self._access_token.encode('utf-8'),
        )

    def require_http_token(self, request: fastapi.Request) -> None:
        """A FastAPI dependency that rejects HTTP requests without the token.

        Args:
            request (fastapi.Request): The incoming request.

        Raises:
            fastapi.HTTPException: The Authorization header is missing or holds the wrong token (status 401).
        """
        header = request.headers.get('authorization', '')
        presented_token = None
        if header.startswith(_BEARER_PREFIX):
            presented_token = header.removeprefix(_BEARER_PREFIX)
        if not self.is_valid(presented_token):
            raise fastapi.HTTPException(
                status_code=401,
                detail='Missing or wrong access token',
            )
