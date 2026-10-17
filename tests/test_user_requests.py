"""Tests for the desks' questions and plans to the user: the tools, the store, the responses and the routes."""

import asyncio
import dataclasses
import datetime
from pathlib import Path

import fastapi
import fastapi.testclient
import pydantic
import pytest

from trading_agent.gateway import access_guard
from trading_agent.gateway.routes import request_routes
from trading_agent.requests import user_request as user_request_module
from trading_agent.requests import user_request_responder
from trading_agent.requests import user_request_store
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.tools import ask_user_tool
from trading_agent.tools import present_plan_tool
from trading_agent.workspace import workspace_layout

_TOKEN = 'test-access-token'


class _StandInDesk:
    """A desk that keeps what it is sent.

    Attributes:
        triggers: The triggers submitted.
    """

    def __init__(self):
        """Creates the desk."""
        self.triggers: list[trigger_module.Trigger] = []

    def submit(self, trigger: trigger_module.Trigger) -> None:
        """Keeps a trigger.

        Args:
            trigger (trigger_module.Trigger): The trigger.
        """
        self.triggers.append(trigger)


class _Setup:
    """A store, a bus, one stand-in desk, the two tools and the responder.

    Attributes:
        store: The request store.
        event_bus: The event bus.
        desk: The stand-in desk.
        ask_user: The ask_user tool.
        present_plan: The present_plan tool.
        responder: The responder.
    """

    def __init__(self, directory: Path):
        """Builds everything in a scratch workspace.

        Args:
            directory (Path): The scratch folder.
        """
        layout = workspace_layout.WorkspaceLayout(directory)
        self.store = user_request_store.UserRequestStore(layout)
        self.event_bus = event_bus_module.EventBus()
        self.desk = _StandInDesk()
        self.ask_user = ask_user_tool.AskUserTool(self.store, self.event_bus, 'main')
        self.present_plan = present_plan_tool.PresentPlanTool(self.store, self.event_bus, 'main')
        self.responder = user_request_responder.UserRequestResponder(
            self.store,
            self.event_bus,
            {
                'main': self.desk,
            },
        )

    def ask(self, multi_select: bool = False) -> user_request_module.UserRequest:
        """Asks one question with two options.

        Args:
            multi_select (bool): Whether several options may be chosen.

        Returns:
            user_request_module.UserRequest: The saved request.
        """
        arguments = ask_user_tool.AskUserArguments(
            questions=[
                ask_user_tool.Question(
                    question='Which stop loss should the desk use?',
                    header='Stop loss',
                    options=[
                        ask_user_tool.QuestionOption(label='1% (Recommended)', description='Tight stop'),
                        ask_user_tool.QuestionOption(label='2%', description='Wider stop', preview='| Level | Price |\n|---|---|\n| Stop | 98 |'),
                    ],
                    multi_select=multi_select,
                ),
            ]
        )
        asyncio.run(self.ask_user.run(arguments))
        return self.store.pending()[-1]

    def plan(self) -> user_request_module.UserRequest:
        """Presents one plan.

        Returns:
            user_request_module.UserRequest: The saved request.
        """
        arguments = present_plan_tool.PresentPlanArguments(
            title='Monday pre-market plan',
            plan='## Plan\n- Watch NIFTY at 23,100\n- No trades before 09:30',
        )
        asyncio.run(self.present_plan.run(arguments))
        return self.store.pending()[-1]


def _option(label: str) -> ask_user_tool.QuestionOption:
    """Builds an option with a fixed description.

    Args:
        label (str): The option's label.

    Returns:
        ask_user_tool.QuestionOption: The option.
    """
    return ask_user_tool.QuestionOption(label=label, description='A choice')


class TestAskUserArguments:
    """Tests for the checks on ask_user's arguments."""

    def test_other_is_refused_because_it_is_added_automatically(self) -> None:
        """An option labelled Other is refused."""
        with pytest.raises(pydantic.ValidationError):
            ask_user_tool.Question(
                question='Which?',
                header='Choice',
                options=[
                    _option('A'),
                    _option('Other'),
                ],
            )

    def test_duplicate_labels_are_refused(self) -> None:
        """Two options with the same label are refused."""
        with pytest.raises(pydantic.ValidationError):
            ask_user_tool.Question(
                question='Which?',
                header='Choice',
                options=[
                    _option('A'),
                    _option('a'),
                ],
            )

    def test_long_header_and_single_option_are_refused(self) -> None:
        """A header over 12 characters, or only one option, is refused."""
        with pytest.raises(pydantic.ValidationError):
            ask_user_tool.Question(
                question='Which?',
                header='A very long header',
                options=[
                    _option('A'),
                    _option('B'),
                ],
            )
        with pytest.raises(pydantic.ValidationError):
            ask_user_tool.Question(
                question='Which?',
                header='Choice',
                options=[
                    _option('A'),
                ],
            )


class TestTools:
    """Tests for ask_user and present_plan."""

    def test_question_is_saved_and_published(self, tmp_path: Path) -> None:
        """Asking saves a pending question request and publishes it."""
        setup = _Setup(tmp_path)
        with setup.event_bus.subscribe() as subscription:
            request = setup.ask()
            published = subscription._queue.get_nowait()

        assert request.kind == user_request_module.QUESTION
        assert request.status == user_request_module.PENDING
        assert request.content['questions'][0]['options'][1]['preview'].startswith('| Level')
        assert published.kind == event_module.EventKind.USER_REQUEST
        assert published.payload['request_id'] == request.request_id

    def test_plan_is_saved_with_its_title(self, tmp_path: Path) -> None:
        """Presenting a plan saves a pending plan request."""
        setup = _Setup(tmp_path)

        request = setup.plan()

        assert request.kind == user_request_module.PLAN
        assert request.title() == 'Monday pre-market plan'


class TestResponder:
    """Tests for answering, deciding and dismissing."""

    def test_answer_reaches_the_desk_as_a_message_naming_the_request(self, tmp_path: Path) -> None:
        """An answer is saved, and the desk gets a user message with the answer and the request id."""
        setup = _Setup(tmp_path)
        request = setup.ask()

        answered = setup.responder.answer_question(
            request.request_id,
            [
                {
                    'selected': [
                        '2%',
                    ],
                    'other': '',
                },
            ],
            'web',
        )

        assert answered.status == user_request_module.ANSWERED
        assert answered.responded_via == 'web'
        trigger = setup.desk.triggers[-1]
        assert trigger.source == trigger_module.TriggerSource.USER_MESSAGE
        assert trigger.request_id == request.request_id
        assert '"2%"' in trigger.text
        assert trigger.to_json_dictionary()['request_id'] == request.request_id

    def test_other_text_counts_as_the_answer(self, tmp_path: Path) -> None:
        """Text typed under Other is a valid single answer and is passed on."""
        setup = _Setup(tmp_path)
        request = setup.ask()

        setup.responder.answer_question(
            request.request_id,
            [
                {
                    'selected': [],
                    'other': 'Use 1.5%',
                },
            ],
            'web',
        )

        assert 'Use 1.5%' in setup.desk.triggers[-1].text

    def test_single_choice_with_two_answers_is_refused(self, tmp_path: Path) -> None:
        """A single-choice question with two answers is refused and stays pending."""
        setup = _Setup(tmp_path)
        request = setup.ask()

        with pytest.raises(ValueError):
            setup.responder.answer_question(
                request.request_id,
                [
                    {
                        'selected': [
                            '2%',
                        ],
                        'other': 'Also this',
                    },
                ],
                'web',
            )

        assert setup.store.get(request.request_id).status == user_request_module.PENDING
        assert setup.desk.triggers == []

    def test_multiple_choice_accepts_several_answers(self, tmp_path: Path) -> None:
        """A multiple-choice question accepts several options."""
        setup = _Setup(tmp_path)
        request = setup.ask(multi_select=True)

        setup.responder.answer_question(
            request.request_id,
            [
                {
                    'selected': [
                        '1% (Recommended)',
                        '2%',
                    ],
                    'other': '',
                },
            ],
            'web',
        )

        assert setup.store.get(request.request_id).status == user_request_module.ANSWERED

    def test_unknown_option_is_refused(self, tmp_path: Path) -> None:
        """An option the question does not have is refused."""
        setup = _Setup(tmp_path)
        request = setup.ask()

        with pytest.raises(ValueError):
            setup.responder.answer_question(
                request.request_id,
                [
                    {
                        'selected': [
                            '5%',
                        ],
                        'other': '',
                    },
                ],
                'web',
            )

    def test_a_request_is_answered_only_once(self, tmp_path: Path) -> None:
        """A second answer to the same request is refused."""
        setup = _Setup(tmp_path)
        request = setup.ask()
        answer = [
            {
                'selected': [
                    '2%',
                ],
                'other': '',
            },
        ]
        setup.responder.answer_question(request.request_id, answer, 'web')

        with pytest.raises(user_request_store.UserRequestError):
            setup.responder.answer_question(request.request_id, answer, 'telegram')

    def test_plan_approval_and_revision(self, tmp_path: Path) -> None:
        """Approving says to carry the plan out; revising needs feedback and passes it on."""
        setup = _Setup(tmp_path)
        first = setup.plan()
        second = setup.plan()

        setup.responder.decide_plan(first.request_id, 'approve', '', 'web')
        with pytest.raises(ValueError):
            setup.responder.decide_plan(second.request_id, 'revise', '', 'web')
        setup.responder.decide_plan(second.request_id, 'revise', 'Smaller size first', 'web')

        assert 'approved your plan' in setup.desk.triggers[0].text
        assert 'Smaller size first' in setup.desk.triggers[1].text

    def test_dismissal_tells_the_desk_to_use_its_judgment(self, tmp_path: Path) -> None:
        """Dismissing closes the request and tells the desk."""
        setup = _Setup(tmp_path)
        request = setup.ask()

        dismissed = setup.responder.dismiss(request.request_id, 'web')

        assert dismissed.status == user_request_module.DISMISSED
        assert 'without answering' in setup.desk.triggers[-1].text

    def test_lapsed_request_is_marked_expired(self, tmp_path: Path) -> None:
        """A request past its expiry time is listed as expired and cannot be answered."""
        setup = _Setup(tmp_path)
        request = setup.ask()
        lapsed = dataclasses.replace(
            request,
            expires_at=(datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1)).isoformat(),
        )
        setup.store.save(lapsed)

        assert setup.store.get(request.request_id).status == user_request_module.EXPIRED
        assert setup.store.pending() == []


class TestRequestRoutes:
    """Tests for the /api/requests routes."""

    def _client(self, setup: _Setup) -> fastapi.testclient.TestClient:
        """Mounts the request routes.

        Args:
            setup (_Setup): The store and responder to use.

        Returns:
            fastapi.testclient.TestClient: The client, sending the access token.
        """
        application = fastapi.FastAPI()
        application.include_router(
            request_routes.RequestRoutes(
                access_guard.AccessGuard(_TOKEN),
                setup.store,
                setup.responder,
            ).router()
        )
        return fastapi.testclient.TestClient(
            application,
            headers={
                'Authorization': f'Bearer {_TOKEN}',
            },
        )

    def test_pending_requests_are_listed_and_answered(self, tmp_path: Path) -> None:
        """A pending request is listed, answered, and then no longer pending."""
        setup = _Setup(tmp_path)
        request = setup.ask()
        client = self._client(setup)

        listed = client.get('/api/requests').json()['requests']
        answered = client.post(
            f'/api/requests/{request.request_id}/answer',
            json={
                'answers': [
                    {
                        'selected': [
                            '2%',
                        ],
                    },
                ],
            },
        )

        assert [item['request_id'] for item in listed] == [
            request.request_id,
        ]
        assert answered.status_code == 200
        assert client.get('/api/requests').json()['requests'] == []
        assert len(client.get('/api/requests?status=all').json()['requests']) == 1

    def test_errors_map_to_status_codes(self, tmp_path: Path) -> None:
        """An unknown request is 404, a bad answer 422, and a second response 409."""
        setup = _Setup(tmp_path)
        request = setup.ask()
        client = self._client(setup)

        missing = client.post('/api/requests/nope/dismiss')
        wrong = client.post(
            f'/api/requests/{request.request_id}/answer',
            json={
                'answers': [
                    {
                        'selected': [
                            '9%',
                        ],
                    },
                ],
            },
        )
        client.post(f'/api/requests/{request.request_id}/dismiss')
        again = client.post(f'/api/requests/{request.request_id}/dismiss')

        assert missing.status_code == 404
        assert wrong.status_code == 422
        assert again.status_code == 409

    def test_plan_decision_route(self, tmp_path: Path) -> None:
        """A plan is approved through its route."""
        setup = _Setup(tmp_path)
        request = setup.plan()
        client = self._client(setup)

        answer = client.post(
            f'/api/requests/{request.request_id}/plan',
            json={
                'decision': 'approve',
            },
        )

        assert answer.status_code == 200
        assert answer.json()['response']['decision'] == 'approve'
