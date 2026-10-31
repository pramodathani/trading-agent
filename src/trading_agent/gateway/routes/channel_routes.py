"""Routes for the messaging channels: Telegram's state and its pairings.

  GET    /api/channels                                  Telegram's state, paired chats and waiting codes
  POST   /api/channels/telegram/pairings/{code}/approve pair the chat that was given a code
  DELETE /api/channels/telegram/chats/{chat_id}         unpair a chat

Typical usage example:

  application.include_router(ChannelRoutes(guard, store, configuration, secrets_present, channel).router())
"""

import dataclasses
from typing import Any

import fastapi

from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.channels import telegram_channel as telegram_channel_module
from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import route_group


class ChannelRoutes(route_group.RouteGroup):
    """The channel routes."""

    def __init__(
        self,
        guard: access_guard.AccessGuard,
        store: pairing_store_module.PairingStore,
        configuration: agent_configuration.TelegramConfiguration,
        token_present: bool,
        channel: telegram_channel_module.TelegramChannel | None,
    ):
        """Creates the routes.

        Args:
            guard (access_guard.AccessGuard): Checks the access token.
            store (pairing_store_module.PairingStore): The pairing file.
            configuration (agent_configuration.TelegramConfiguration): The [telegram] settings.
            token_present (bool): Whether TRADING_AGENT_TELEGRAM_BOT_TOKEN is set.
            channel (telegram_channel_module.TelegramChannel | None): The running channel, or None when Telegram is off.
        """
        super().__init__(guard)
        self._store = store
        self._configuration = configuration
        self._token_present = token_present
        self._channel = channel

    def _add_routes(self, router: fastapi.APIRouter) -> None:
        """Adds the channel routes.

        Args:
            router (fastapi.APIRouter): The router.
        """
        router.add_api_route('/api/channels', self.channels, methods=['GET'])
        router.add_api_route(
            '/api/channels/telegram/pairings/{code}/approve',
            self.approve,
            methods=['POST'],
        )
        router.add_api_route(
            '/api/channels/telegram/chats/{chat_id}',
            self.revoke,
            methods=['DELETE'],
        )

    def channels(self) -> dict[str, Any]:
        """Telegram's state.

        Returns:
            dict[str, Any]: Whether it is enabled and has a token, its connection state, its bot name, the paired chats and the waiting codes.
        """
        state = 'off'
        error = ''
        username = ''
        if self._channel is not None:
            state = self._channel.state
            error = self._channel.error
            username = self._channel.username
        paired = []
        for chat in self._store.paired_chats():
            paired.append(dataclasses.asdict(chat))
        pending = []
        for waiting in self._store.pending():
            pending.append(dataclasses.asdict(waiting))
        return {
            'telegram': {
                'enabled': self._configuration.enabled,
                'token_present': self._token_present,
                'state': state,
                'error': error,
                'username': username,
                'default_trader': self._configuration.default_trader,
                'notifications': self._configuration.notifications,
                'paired': paired,
                'pending': pending,
            },
        }

    async def approve(self, code: str) -> dict[str, Any]:
        """Pairs the chat that was given a code.

        Args:
            code (str): The code.

        Returns:
            dict[str, Any]: The paired chat.

        Raises:
            fastapi.HTTPException: No valid code matches (status 404).
        """
        try:
            if self._channel is not None:
                chat = await self._channel.approve(code)
            else:
                chat = self._store.approve(
                    code, self._configuration.default_trader
                )
        except pairing_store_module.PairingError as error:
            raise fastapi.HTTPException(
                status_code=404, detail=str(error)
            ) from error
        return dataclasses.asdict(chat)

    def revoke(self, chat_id: int) -> dict[str, Any]:
        """Unpairs a chat.

        Args:
            chat_id (int): The chat.

        Returns:
            dict[str, Any]: The chat that was removed.

        Raises:
            fastapi.HTTPException: The chat is not paired (status 404).
        """
        try:
            chat = self._store.revoke(chat_id)
        except pairing_store_module.PairingError as error:
            raise fastapi.HTTPException(
                status_code=404, detail=str(error)
            ) from error
        return dataclasses.asdict(chat)
