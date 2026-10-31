"""Sends one push notification to one phone through Firebase Cloud Messaging.

Firebase's HTTP v1 API needs a short-lived OAuth access token, which google-auth makes from the service-account key file the user downloaded from the Firebase console. The token lasts about an hour and is renewed when it runs out. The Firebase project is read from the same key file.

The notification's title and text pass through Google's servers on their way to the phone.

Typical usage example:

  sender = FirebaseSender(Path('/home/pramod/.config/trading-agent/firebase.json'))
  outcome = await sender.send(token, 'scalper', 'COMPLETE buy 50 RELIANCE', {'trader': 'scalper'})
"""

import asyncio
import logging
from collections.abc import Mapping
from pathlib import Path

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import service_account

_LOGGER = logging.getLogger(__name__)
_SCOPE = 'https://www.googleapis.com/auth/firebase.messaging'
_SEND_ADDRESS = 'https://fcm.googleapis.com/v1/projects/{project}/messages:send'
_TIMEOUT_SECONDS = 15.0
_LONGEST_TITLE = 120
_LONGEST_BODY = 1000
ANDROID_CHANNEL = 'trading'


class FirebaseSender:
    """Sends notifications with one Firebase project's key."""

    SENT = 'sent'
    UNREGISTERED = 'unregistered'
    FAILED = 'failed'

    def __init__(
        self,
        service_account_file: Path,
        client: httpx.AsyncClient | None = None,
    ):
        """Reads the key file without contacting Google.

        Args:
            service_account_file (Path): The service-account key JSON from the Firebase console.
            client (httpx.AsyncClient | None): The HTTP client to send with; None makes one.

        Raises:
            ValueError: The file is not a service-account key.
            FileNotFoundError: The file does not exist.
        """
        self._credentials = (
            service_account.Credentials.from_service_account_file(
                str(service_account_file),
                scopes=[
                    _SCOPE,
                ],
            )
        )
        self.project_id = self._credentials.project_id
        if not self.project_id:
            raise ValueError(
                f'The Firebase key file has no project_id: {service_account_file}'
            )
        self._client = client or httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
        self._refresh_lock = asyncio.Lock()

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: Mapping[str, str],
    ) -> str:
        """Sends one notification.

        Args:
            token (str): The phone's Firebase Cloud Messaging token.
            title (str): The notification's title, such as the trader's name.
            body (str): The notification's text.
            data (Mapping[str, str]): Values the app reads when the notification is tapped, such as the trader.

        Returns:
            str: SENT, UNREGISTERED when Firebase says the token is no longer valid, or FAILED for any other problem.
        """
        try:
            access_token = await self._access_token()
            response = await self._client.post(
                _SEND_ADDRESS.format(project=self.project_id),
                headers={
                    'Authorization': f'Bearer {access_token}',
                },
                json=self._message(token, title, body, data),
            )
        except Exception:
            _LOGGER.exception('Could not reach Firebase Cloud Messaging')
            return self.FAILED
        if response.status_code == 200:
            return self.SENT
        if response.status_code == 404 or 'UNREGISTERED' in response.text:
            return self.UNREGISTERED
        _LOGGER.warning(
            'Firebase Cloud Messaging refused a notification (status %s): %s',
            response.status_code,
            response.text[:500],
        )
        return self.FAILED

    def _message(
        self,
        token: str,
        title: str,
        body: str,
        data: Mapping[str, str],
    ) -> dict:
        """Builds the HTTP v1 message.

        Args:
            token (str): The phone's token.
            title (str): The title.
            body (str): The text.
            data (Mapping[str, str]): Values for the app.

        Returns:
            dict: The JSON body for messages:send.
        """
        return {
            'message': {
                'token': token,
                'notification': {
                    'title': title[:_LONGEST_TITLE],
                    'body': body[:_LONGEST_BODY],
                },
                'data': dict(data),
                'android': {
                    'priority': 'HIGH',
                    'notification': {
                        'channel_id': ANDROID_CHANNEL,
                    },
                },
            },
        }

    async def _access_token(self) -> str:
        """Gives a valid OAuth access token, renewing it when it has run out.

        Returns:
            str: The token.
        """
        async with self._refresh_lock:
            if not self._credentials.valid:
                await asyncio.to_thread(
                    self._credentials.refresh, google_requests.Request()
                )
            return self._credentials.token
