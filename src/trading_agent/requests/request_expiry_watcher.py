"""Notices requests that lapsed without an answer, and tells their traders.

Permission requests lapse after [approvals] expiry_minutes, because an action approved much later could act on stale prices. The watcher runs beside the traders and checks every few seconds.

Typical usage example:

  watcher = RequestExpiryWatcher(store, responder)
  await watcher.run()
"""

import asyncio
import logging

from trading_agent.requests import (
    user_request_responder as user_request_responder_module,
)
from trading_agent.requests import (
    user_request_store as user_request_store_module,
)

_LOGGER = logging.getLogger(__name__)
_CHECK_SECONDS = 15.0


class RequestExpiryWatcher:
    """Saves lapsed requests as expired and tells each trader once."""

    def __init__(
        self,
        store: user_request_store_module.UserRequestStore,
        responder: user_request_responder_module.UserRequestResponder,
        check_seconds: float = _CHECK_SECONDS,
    ):
        """Creates the watcher.

        Args:
            store (user_request_store_module.UserRequestStore): Where requests are kept.
            responder (user_request_responder_module.UserRequestResponder): Tells the traders.
            check_seconds (float): How long to wait between checks.
        """
        self._store = store
        self._responder = responder
        self._check_seconds = check_seconds

    def check(self) -> int:
        """Expires every lapsed request now and tells its trader.

        Returns:
            int: How many requests expired.
        """
        expired = self._store.expire_lapsed()
        for request in expired:
            self._responder.report_expired(request)
        return len(expired)

    async def run(self) -> None:
        """Checks every few seconds until cancelled."""
        while True:
            try:
                self.check()
            except OSError as error:
                _LOGGER.warning(
                    'Could not check for lapsed requests: %s', error
                )
            await asyncio.sleep(self._check_seconds)
