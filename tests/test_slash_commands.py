"""Tests for slash commands and the context line, run through a real desk loop."""

import asyncio

from trading_agent.backends import model_router
from trading_agent.configuration import agent_configuration
from trading_agent.runtime import desk_runtime
from trading_agent.runtime import event as event_module
from trading_agent.runtime import event_bus as event_bus_module
from trading_agent.runtime import trigger as trigger_module
from trading_agent.runtime import turn_runner


class _RecordingRunner(turn_runner.TurnRunner):
    """A turn runner that records what it was asked and whether it was reset.

    Attributes:
        received_texts: The trigger texts it was given.
        reset_count: How many times reset was called.
    """

    def __init__(self, name: str):
        """Creates the runner.

        Args:
            name (str): Used in the answer.
        """
        self._name = name
        self.received_texts = []
        self.reset_count = 0

    async def run_turn(
        self,
        trigger: trigger_module.Trigger,
    ) -> turn_runner.TurnResult:
        """Records the text and answers.

        Args:
            trigger (trigger_module.Trigger): The turn's trigger.

        Returns:
            turn_runner.TurnResult: "<name> answered".
        """
        self.received_texts.append(trigger.text)
        return turn_runner.TurnResult(text=f'{self._name} answered')

    async def reset(self) -> None:
        """Counts the reset."""
        self.reset_count += 1


class _Desk:
    """A desk with a two-backend router, driven one message at a time.

    Attributes:
        claude: The first backend's runner.
        gemma: The second backend's runner.
        desk: The desk.
    """

    def __init__(self):
        """Builds the desk."""
        self.claude = _RecordingRunner('claude')
        self.gemma = _RecordingRunner('gemma')
        self._event_bus = event_bus_module.EventBus()
        router = model_router.ModelRouter(
            'main',
            [
                model_router.BackendRoute('claude', self.claude),
                model_router.BackendRoute('gemma', self.gemma),
            ],
            self._event_bus,
        )
        self.desk = desk_runtime.DeskRuntime(
            agent_configuration.DeskConfiguration(name='main'),
            self._event_bus,
            router,
            'dry_run',
        )

    def send(self, texts: list[str]) -> list[str]:
        """Sends messages in order and collects each reply.

        Args:
            texts (list[str]): The messages.

        Returns:
            list[str]: The reply to each message.
        """

        async def scenario() -> list[str]:
            """Runs the desk loop until every message is answered.

            Returns:
                list[str]: The replies.
            """
            replies = []
            with self._event_bus.subscribe() as subscription:
                task = asyncio.create_task(self.desk.run())
                for text in texts:
                    self.desk.submit(
                        trigger_module.Trigger.now(
                            trigger_module.TriggerSource.USER_MESSAGE,
                            'main',
                            text,
                        )
                    )
                while len(replies) < len(texts):
                    received = await asyncio.wait_for(
                        subscription.next_event(),
                        timeout=2,
                    )
                    if received.kind == event_module.EventKind.TEXT:
                        replies.append(received.payload['text'])
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            return replies

        return asyncio.run(scenario())


class TestSlashCommands:
    """Tests for the commands and the context line."""

    def test_status_lists_the_models_without_asking_one(self) -> None:
        """/status describes the desk and its backends, and no model is asked."""
        setup = _Desk()

        reply = setup.send(['/status'])[0]

        assert 'Desk: main' in reply
        assert 'Mode: dry_run' in reply
        assert '1. claude: ready' in reply
        assert setup.claude.received_texts == []

    def test_model_command_changes_the_order_and_auto_restores_it(self) -> None:
        """/model gemma puts gemma first; /model auto goes back to the configured order."""
        setup = _Desk()

        replies = setup.send(
            [
                '/model gemma',
                'hello',
                '/model auto',
                'hello again',
            ]
        )

        assert '1. gemma' in replies[0]
        assert replies[1] == 'gemma answered'
        assert '1. claude' in replies[2]
        assert replies[3] == 'claude answered'

    def test_unknown_model_name_is_refused(self) -> None:
        """/model with a name the desk does not have lists the real ones."""
        reply = _Desk().send(['/model gpt'])[0]

        assert "No backend named 'gpt'" in reply

    def test_paused_desk_does_not_ask_any_model(self) -> None:
        """While paused, messages get a fixed reply; after /resume the model answers again."""
        setup = _Desk()

        replies = setup.send(
            [
                '/pause',
                'buy something',
                '/resume',
                'hello',
            ]
        )

        assert 'paused' in replies[1]
        assert replies[3] == 'claude answered'
        assert len(setup.claude.received_texts) == 1

    def test_new_resets_every_backend(self) -> None:
        """/new resets each backend's conversation."""
        setup = _Desk()

        setup.send(['/new'])

        assert setup.claude.reset_count == 1
        assert setup.gemma.reset_count == 1

    def test_later_and_unknown_commands_explain_themselves(self) -> None:
        """Commands from later milestones say when they arrive; unknown ones point to /help."""
        replies = _Desk().send(
            [
                '/think',
                '/frobnicate',
            ]
        )

        assert 'later milestone' in replies[0]
        assert '/help' in replies[1]

    def test_model_sees_the_india_time_and_trigger_source(self) -> None:
        """The message the model receives starts with the context line."""
        setup = _Desk()

        setup.send(['What is the time?'])

        first_line, _, rest = setup.claude.received_texts[0].partition('\n')
        assert first_line.startswith('[India time: ')
        assert first_line.endswith('IST · woken by: user_message]')
        assert rest == 'What is the time?'
