"""Tests for choosing a trader's first model through POST /api/traders/{trader}/model."""

import fastapi
import fastapi.testclient

from trading_agent.backends import model_router
from trading_agent.configuration import agent_configuration
from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import trader_routes
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner

_TOKEN = 'test-access-token'


class _AnsweringRunner(turn_runner.TurnRunner):
    """A turn runner that always answers, with a model that can be switched.

    Attributes:
        model: The model in use.
    """

    def __init__(self, model: str = 'configured'):
        """Creates the runner.

        Args:
            model (str): The configured model.
        """
        self._configured = model
        self.model = model

    def active_model(self) -> str | None:
        """The model in use.

        Returns:
            str | None: The model.
        """
        return self.model

    def use_model(self, model: str | None) -> None:
        """Switches the model.

        Args:
            model (str | None): The model, or None for the configured one.
        """
        self.model = model or self._configured

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Answers at once.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.

        Returns:
            turn_runner.TurnResult: A fixed answer.
        """
        del trigger
        return turn_runner.TurnResult(text='answered')


class _StandInTrader:
    """Stands in for a trader runtime with the fields the trader summary reads.

    Attributes:
        name: The trader's name.
        state: Its state.
        paused: Whether it is paused.
        queued_count: How many triggers wait.
        turn_runner: Its runner.
    """

    def __init__(self, runner: turn_runner.TurnRunner):
        """Creates the trader.

        Args:
            runner (turn_runner.TurnRunner): The trader's runner.
        """
        self.name = 'main'
        self.state = 'idle'
        self.paused = False
        self.queued_count = 0
        self.turn_runner = runner


def _router() -> model_router.ModelRouter:
    """Builds a router with two backends.

    Returns:
        model_router.ModelRouter: The router, claude first.
    """
    return model_router.ModelRouter(
        'main',
        [
            model_router.BackendRoute('claude', _AnsweringRunner('opus')),
            model_router.BackendRoute('qwen', _AnsweringRunner('qwen3.8:27b')),
        ],
        event_bus_module.EventBus(),
    )


def _client(runner: turn_runner.TurnRunner) -> fastapi.testclient.TestClient:
    """Builds a client for the trader routes with one trader.

    Args:
        runner (turn_runner.TurnRunner): The trader's runner.

    Returns:
        fastapi.testclient.TestClient: The client, sending the access token.
    """
    application = fastapi.FastAPI()
    application.include_router(
        trader_routes.TraderRoutes(
            {
                'main': _StandInTrader(runner),
            },
            access_guard.AccessGuard(_TOKEN),
            backend_configurations={
                'claude': agent_configuration.BackendConfiguration(
                    kind='claude_code',
                    model='opus',
                    context_window=1000000,
                    other_models=[
                        'claude-haiku-5-5',
                    ],
                ),
                'qwen': agent_configuration.BackendConfiguration(
                    kind='ollama',
                    base_url='http://127.0.0.1:11434',
                    model='qwen3.8:27b',
                    context_window=32768,
                ),
            },
        ).router()
    )
    return fastapi.testclient.TestClient(
        application,
        headers={
            'Authorization': f'Bearer {_TOKEN}',
        },
    )


class TestModelChoiceRoute:
    """Tests for POST /api/traders/{trader}/model and the backends in the trader summary."""

    def test_summary_lists_backends_with_their_models(self) -> None:
        """The trader summary names each backend and its model, in order."""
        client = _client(_router())

        body = client.get('/api/traders').json()

        assert body['traders'][0]['backends'] == [
            {
                'name': 'claude',
                'kind': 'claude_code',
                'model': 'opus',
                'active_model': 'opus',
                'other_models': [
                    'claude-haiku-5-5',
                ],
            },
            {
                'name': 'qwen',
                'kind': 'ollama',
                'model': 'qwen3.8:27b',
                'active_model': 'qwen3.8:27b',
                'other_models': [],
            },
        ]

    def test_choosing_a_backend_makes_it_preferred(self) -> None:
        """A named backend becomes the preferred one, and null returns to the configured order."""
        router = _router()
        client = _client(router)

        chosen = client.post(
            '/api/traders/main/model', json={'backend': 'qwen'}
        )

        assert chosen.status_code == 200
        assert chosen.json()['preferred_model'] == 'qwen'
        assert router.preferred_backend_name == 'qwen'
        cleared = client.post('/api/traders/main/model', json={'backend': None})
        assert cleared.json()['preferred_model'] is None

    def test_unknown_backend_is_refused(self) -> None:
        """A backend the trader does not have answers 400."""
        client = _client(_router())

        answer = client.post('/api/traders/main/model', json={'backend': 'gpt'})

        assert answer.status_code == 400

    def test_trader_without_models_is_refused(self) -> None:
        """A trader whose runner is not a model router answers 409."""
        client = _client(_AnsweringRunner())

        answer = client.post(
            '/api/traders/main/model', json={'backend': 'qwen'}
        )

        assert answer.status_code == 409

    def test_another_model_of_a_backend_can_be_chosen_and_undone(self) -> None:
        """Choosing an offered model switches that backend to it; Auto switches it back."""
        router = _router()
        client = _client(router)

        chosen = client.post(
            '/api/traders/main/model',
            json={'backend': 'claude', 'model': 'claude-haiku-5-5'},
        )
        auto = client.post('/api/traders/main/model', json={'backend': None})

        assert chosen.status_code == 200
        assert (
            chosen.json()['backends'][0]['active_model'] == 'claude-haiku-5-5'
        )
        assert chosen.json()['preferred_model'] == 'claude'
        assert auto.json()['backends'][0]['active_model'] == 'opus'

    def test_model_not_offered_is_refused(self) -> None:
        """A model missing from the backend's other_models answers 400."""
        client = _client(_router())

        answer = client.post(
            '/api/traders/main/model',
            json={'backend': 'claude', 'model': 'claude-unknown'},
        )

        assert answer.status_code == 400
