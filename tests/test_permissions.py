"""Tests for permission prompts: the gate that holds a call, the user's decision, standing permissions, expiry, the routes and Telegram's buttons."""

import asyncio
import dataclasses
import datetime
from pathlib import Path

import fastapi
import fastapi.testclient
import pytest

from tests import fakes
from tests import test_telegram_requests
from tests import test_user_requests
from trading_agent.agent import loop_guard
from trading_agent.agent import messages
from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.channels import telegram_api
from trading_agent.channels import telegram_requests
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import request_routes
from trading_agent.requests import permission_gate
from trading_agent.requests import permission_grants
from trading_agent.requests import request_expiry_watcher
from trading_agent.requests import user_request as user_request_module
from trading_agent.requests import user_request_responder
from trading_agent.requests import user_request_store
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import tool_call_executor
from trading_agent.tools import tool_registry
from trading_agent.workspace import workspace_layout

_TOKEN = 'test-access-token'
_OWNER = 111


class _Permissions:
    """A trader whose echo tool needs permission, with its executor, responder and watcher.

    Attributes:
        store: The request store.
        grants: The standing permissions.
        trader: The stand-in trader.
        executor: The trader's executor, with the gate.
        responder: The responder, able to run the trader's tools.
        watcher: The expiry watcher.
    """

    def __init__(self, directory: Path):
        """Builds everything in a scratch workspace.

        Args:
            directory (Path): The scratch folder.
        """
        layout = workspace_layout.WorkspaceLayout(directory)
        event_bus = event_bus_module.EventBus()
        self.store = user_request_store.UserRequestStore(layout)
        self.grants = permission_grants.PermissionGrants(layout)
        registry = tool_registry.ToolRegistry(
            [
                fakes.EchoTool(),
            ],
            timeout_seconds=1,
        )
        gate = permission_gate.PermissionGate(
            [
                'echo',
            ],
            5,
            self.store,
            self.grants,
            event_bus,
        )
        self.executor = tool_call_executor.ToolCallExecutor(
            'main',
            registry,
            event_bus,
            loop_guard.LoopGuard(maximum_identical_calls=5),
            gate,
        )
        self.trader = test_user_requests._StandInTrader()
        self.responder = user_request_responder.UserRequestResponder(
            self.store,
            event_bus,
            {
                'main': self.trader,
            },
            {
                'main': registry,
            },
            self.grants,
        )
        self.watcher = request_expiry_watcher.RequestExpiryWatcher(
            self.store, self.responder
        )

    def call(self, word: str = 'hello') -> str:
        """Has the trader call the echo tool.

        Args:
            word (str): The word to echo.

        Returns:
            str: What the model is told.
        """
        trigger = trigger_module.Trigger.now(
            trigger_module.TriggerSource.USER_MESSAGE, 'main', 'go'
        )
        result = asyncio.run(
            self.executor.execute(
                trigger, messages.ToolCall.new('echo', {'word': word})
            )
        )
        return result.text

    def decide(
        self, decision: str, reason: str = ''
    ) -> user_request_module.UserRequest:
        """Decides the newest pending request.

        Args:
            decision (str): "allow_once", "always_allow" or "deny".
            reason (str): The reason, if any.

        Returns:
            user_request_module.UserRequest: The decided request.
        """
        request = self.store.pending()[-1]
        return asyncio.run(
            self.responder.decide_permission(
                request.request_id, decision, reason, 'web'
            )
        )


class TestPermissionGate:
    """Tests for holding calls and deciding them."""

    def test_covered_call_is_held_not_run(self, tmp_path: Path) -> None:
        """A covered call is saved as a permission request with an expiry, and the tool does not run."""
        permissions = _Permissions(tmp_path)

        told = permissions.call('hello')

        request = permissions.store.pending()[0]
        assert 'HELLO' not in told
        assert 'needs the user' in told
        assert request.kind == user_request_module.PERMISSION
        assert request.content['arguments'] == {
            'word': 'hello',
        }
        assert request.expires_at is not None

    def test_allow_once_runs_exactly_the_held_call(
        self, tmp_path: Path
    ) -> None:
        """Allowing runs the held call and gives the trader its result, without a standing permission."""
        permissions = _Permissions(tmp_path)
        permissions.call('hello')

        decided = permissions.decide('allow_once')

        assert decided.response['result'] == 'HELLO'
        assert 'HELLO' in permissions.trader.triggers[-1].text
        assert permissions.grants.all() == []
        assert 'needs the user' in permissions.call('again')

    def test_always_allow_lets_later_calls_through(
        self, tmp_path: Path
    ) -> None:
        """Always allow saves a grant, so the next call runs at once, until it is revoked."""
        permissions = _Permissions(tmp_path)
        permissions.call('hello')

        permissions.decide('always_allow')
        later = permissions.call('later')
        permissions.grants.revoke('main', 'echo')
        after_revoking = permissions.call('again')

        assert later == 'LATER'
        assert 'needs the user' in after_revoking

    def test_deny_does_not_run_and_passes_the_reason(
        self, tmp_path: Path
    ) -> None:
        """Denying does not run the call and tells the trader the reason."""
        permissions = _Permissions(tmp_path)
        permissions.call('hello')

        decided = permissions.decide('deny', 'Not during the opening')

        assert 'result' not in decided.response
        assert 'Not during the opening' in permissions.trader.triggers[-1].text
        assert 'HELLO' not in permissions.trader.triggers[-1].text

    def test_lapsed_request_cannot_be_allowed_and_is_reported_once(
        self, tmp_path: Path
    ) -> None:
        """A lapsed request is refused, and the watcher tells the trader exactly once."""
        permissions = _Permissions(tmp_path)
        permissions.call('hello')
        request = permissions.store.pending()[0]
        permissions.store.save(
            dataclasses.replace(
                request,
                expires_at=(
                    datetime.datetime.now(datetime.UTC)
                    - datetime.timedelta(seconds=1)
                ).isoformat(),
            )
        )

        with pytest.raises(user_request_store.UserRequestError):
            asyncio.run(
                permissions.responder.decide_permission(
                    request.request_id, 'allow_once', '', 'web'
                )
            )
        first = permissions.watcher.check()
        second = permissions.watcher.check()

        assert first == 1
        assert second == 0
        assert 'lapsed' in permissions.trader.triggers[-1].text
        assert (
            permissions.store.get(request.request_id).status
            == user_request_module.EXPIRED
        )

    def test_uncovered_tools_run_at_once(self, tmp_path: Path) -> None:
        """A gate that covers other tools lets the call run."""
        layout = workspace_layout.WorkspaceLayout(tmp_path)
        store = user_request_store.UserRequestStore(layout)
        gate = permission_gate.PermissionGate(
            [
                'flatten_trader',
            ],
            5,
            store,
            permission_grants.PermissionGrants(layout),
            event_bus_module.EventBus(),
        )

        assert not gate.needs_permission('main', 'echo')
        assert gate.needs_permission('main', 'flatten_trader')


class TestPermissionRoutes:
    """Tests for the permission routes."""

    def _client(
        self, permissions: _Permissions
    ) -> fastapi.testclient.TestClient:
        """Mounts the request routes.

        Args:
            permissions (_Permissions): The store, responder and grants to use.

        Returns:
            fastapi.testclient.TestClient: The client, sending the access token.
        """
        application = fastapi.FastAPI()
        application.include_router(
            request_routes.RequestRoutes(
                access_guard.AccessGuard(_TOKEN),
                permissions.store,
                permissions.responder,
                permissions.grants,
            ).router()
        )
        return fastapi.testclient.TestClient(
            application,
            headers={
                'Authorization': f'Bearer {_TOKEN}',
            },
        )

    def test_always_allow_then_list_and_revoke(self, tmp_path: Path) -> None:
        """Always allow through the route runs the call, lists the grant, and the grant can be revoked once."""
        permissions = _Permissions(tmp_path)
        permissions.call('hello')
        request = permissions.store.pending()[0]
        client = self._client(permissions)

        decided = client.post(
            f'/api/requests/{request.request_id}/permission',
            json={'decision': 'always_allow'},
        )
        listed = client.get('/api/permissions').json()['grants']
        revoked = client.post(
            '/api/permissions/revoke',
            json={'trader': 'main', 'tool_name': 'echo'},
        )
        again = client.post(
            '/api/permissions/revoke',
            json={'trader': 'main', 'tool_name': 'echo'},
        )

        assert decided.status_code == 200
        assert decided.json()['response']['result'] == 'HELLO'
        assert [(grant['trader'], grant['tool_name']) for grant in listed] == [
            (
                'main',
                'echo',
            ),
        ]
        assert revoked.status_code == 200
        assert again.status_code == 404

    def test_bad_decision_is_refused(self, tmp_path: Path) -> None:
        """A decision that is not allow_once, always_allow or deny is 422."""
        permissions = _Permissions(tmp_path)
        permissions.call('hello')
        request = permissions.store.pending()[0]

        answer = self._client(permissions).post(
            f'/api/requests/{request.request_id}/permission',
            json={'decision': 'maybe'},
        )

        assert answer.status_code == 422


class TestTelegramPermissions:
    """Tests for permission requests on Telegram."""

    def test_allow_button_runs_the_call(self, tmp_path: Path) -> None:
        """A permission request shows three buttons, and Allow once runs the held call."""
        permissions = _Permissions(tmp_path)
        pairing = pairing_store_module.PairingStore(
            tmp_path / 'telegram_pairing.json'
        )
        pairing.approve(pairing.request(_OWNER, 'Owner'), 'main')
        api = test_telegram_requests._StandInApi()
        handler = telegram_requests.TelegramRequests(
            api, pairing, permissions.store, permissions.responder
        )
        permissions.call('hello')
        request = permissions.store.pending()[0]

        asyncio.run(handler.show(request))
        _, message_id, text, rows = api.sent[0]
        allow = rows[0][0]
        asyncio.run(
            handler.press(
                telegram_api.IncomingButton(
                    chat_id=_OWNER,
                    sender_name='Owner',
                    callback_id='press',
                    data=allow[1],
                    message_id=message_id,
                )
            )
        )

        assert 'wants to run echo' in text
        assert [label for row in rows for label, _ in row] == [
            '✅ Allow once',
            'Always allow echo',
            '⛔ Deny',
        ]
        assert (
            permissions.store.get(request.request_id).response['result']
            == 'HELLO'
        )
