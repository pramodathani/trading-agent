"""Tests for ChatTranscript, which groups a desk's events into chat turns as the web page does."""

from typing import Any

from trading_agent.terminal import chat_items
from trading_agent.terminal import chat_transcript


class _Events:
    """Makes events with increasing timestamps, as the gateway sends them."""

    def __init__(self):
        """Starts the clock at 10:00:00."""
        self._second = 0

    def make(self, event_kind: str, **payload: Any) -> dict[str, Any]:
        """Makes one event of the general desk.

        Args:
            event_kind (str): The event's kind.
            **payload (Any): The event's payload.

        Returns:
            dict[str, Any]: The event.
        """
        self._second += 1
        return {
            'kind': event_kind,
            'desk': 'general',
            'payload': payload,
            'created_at': f'2026-10-19T04:30:{self._second:02d}+00:00',
        }


class TestChatTranscript:
    """Tests for turns, tool calls, streaming, steering, stops and requests."""

    def test_a_full_turn(self) -> None:
        """A message, a tool call with its result and an answer make one turn."""
        events = _Events()
        transcript = chat_transcript.ChatTranscript()
        for event in [
            events.make(
                'trigger_received',
                trigger_id='t1',
                source='user_message',
                text='Quote RELIANCE',
            ),
            events.make('turn_started', trigger_id='t1'),
            events.make(
                'tool_call',
                trigger_id='t1',
                call_id='c1',
                name='get_quote',
                arguments={
                    'symbol': 'RELIANCE',
                },
            ),
            events.make(
                'tool_result',
                trigger_id='t1',
                call_id='c1',
                name='get_quote',
                is_error=False,
                text='2945.5',
            ),
            events.make('model_usage', trigger_id='t1', backend='claude'),
            events.make('text', trigger_id='t1', text='It is 2945.5.'),
            events.make('turn_finished', trigger_id='t1'),
        ]:
            transcript.add(event)

        assert len(transcript.items) == 1
        turn = transcript.items[0]
        assert isinstance(turn, chat_items.ChatTurn)
        assert turn.text == 'Quote RELIANCE'
        assert turn.answer == 'It is 2945.5.'
        assert turn.finished
        assert turn.status_text() == 'answered by claude'
        tool = turn.steps[0]
        assert isinstance(tool, chat_items.ToolStep)
        assert tool.result_text == '2945.5'
        assert transcript.running_turn() is None

    def test_streamed_text_is_dropped_when_the_answer_arrives(self) -> None:
        """Text deltas build up while the desk writes and are cleared by the final answer."""
        events = _Events()
        transcript = chat_transcript.ChatTranscript()
        transcript.add(
            events.make(
                'trigger_received', trigger_id='t1', source='user_message'
            )
        )
        transcript.add(events.make('turn_started', trigger_id='t1'))
        transcript.add(events.make('text_delta', trigger_id='t1', text='It '))
        changed = transcript.add(
            events.make('text_delta', trigger_id='t1', text='is')
        )

        assert isinstance(changed, chat_items.ChatTurn)
        assert changed.streaming_text == 'It is'

        transcript.add(events.make('text', trigger_id='t1', text='It is.'))

        assert changed.streaming_text == ''
        assert changed.answer == 'It is.'

    def test_running_tool_and_tool_runs(self) -> None:
        """Tool calls in a row form one run, and the newest unanswered call is the running one."""
        events = _Events()
        transcript = chat_transcript.ChatTranscript()
        transcript.add(
            events.make(
                'trigger_received', trigger_id='t1', source='user_message'
            )
        )
        transcript.add(events.make('turn_started', trigger_id='t1'))
        for call_id in ('c1', 'c2'):
            transcript.add(
                events.make(
                    'tool_call',
                    trigger_id='t1',
                    call_id=call_id,
                    name='bash_run',
                    arguments={},
                )
            )
        turn = transcript.turn('t1')

        assert turn is not None
        assert turn.running_tool() is not None
        assert turn.running_tool().call_id == 'c2'
        segments = turn.segments()
        assert len(segments) == 1
        assert isinstance(segments[0], chat_items.ToolRun)
        assert len(segments[0].steps) == 2

    def test_a_steering_message_shows_inside_the_running_turn(self) -> None:
        """A message handed to the running turn appears inside it and says it was delivered."""
        events = _Events()
        transcript = chat_transcript.ChatTranscript()
        transcript.add(
            events.make(
                'trigger_received', trigger_id='t1', source='user_message'
            )
        )
        transcript.add(events.make('turn_started', trigger_id='t1'))
        transcript.add(
            events.make(
                'trigger_received',
                trigger_id='t2',
                source='user_message',
                text='Also check TCS',
                steering_into='t1',
            )
        )
        changed = transcript.add(
            events.make(
                'steering',
                trigger_id='t2',
                into_trigger_id='t1',
                delivered=True,
            )
        )

        assert len(transcript.items) == 1
        assert changed is transcript.turn('t1')
        step = transcript.turn('t1').steps[0]
        assert isinstance(step, chat_items.SteeringStep)
        assert step.message.status_text() == 'handed to the running turn'

    def test_an_undelivered_steering_message_becomes_its_own_turn(
        self,
    ) -> None:
        """When the running turn ends first, the message is shown as its own turn once it starts."""
        events = _Events()
        transcript = chat_transcript.ChatTranscript()
        transcript.add(
            events.make(
                'trigger_received', trigger_id='t1', source='user_message'
            )
        )
        transcript.add(events.make('turn_started', trigger_id='t1'))
        transcript.add(
            events.make(
                'trigger_received',
                trigger_id='t2',
                source='user_message',
                steering_into='t1',
            )
        )
        transcript.add(events.make('turn_finished', trigger_id='t1'))
        transcript.add(
            events.make(
                'steering',
                trigger_id='t2',
                into_trigger_id='t1',
                delivered=False,
            )
        )
        shown = transcript.add(events.make('turn_started', trigger_id='t2'))

        assert shown is transcript.turn('t2')
        assert len(transcript.items) == 2
        assert transcript.items[1] is transcript.turn('t2')

    def test_a_stopped_turn(self) -> None:
        """A stopped event marks the turn as stopped by the user."""
        events = _Events()
        transcript = chat_transcript.ChatTranscript()
        transcript.add(
            events.make(
                'trigger_received', trigger_id='t1', source='user_message'
            )
        )
        transcript.add(events.make('turn_started', trigger_id='t1'))
        transcript.add(events.make('stopped', trigger_id='t1'))

        assert transcript.turn('t1').status_text() == 'stopped by you'

    def test_requests_join_the_open_turn_and_take_the_answer(self) -> None:
        """A request without a trigger id joins the running turn, and the user's answer updates it."""
        events = _Events()
        transcript = chat_transcript.ChatTranscript()
        transcript.add(
            events.make(
                'trigger_received', trigger_id='t1', source='user_message'
            )
        )
        transcript.add(events.make('turn_started', trigger_id='t1'))
        transcript.add(
            events.make(
                'user_request',
                request_id='r1',
                kind='permission',
                status='pending',
                content={
                    'tool_name': 'flatten_desk',
                },
            )
        )
        changed = transcript.add(
            events.make(
                'user_response',
                request_id='r1',
                kind='permission',
                status='answered',
                response={
                    'decision': 'deny',
                },
                via='web',
            )
        )

        assert changed is transcript.turn('t1')
        step = transcript.turn('t1').steps[0]
        assert isinstance(step, chat_items.RequestStep)
        assert step.request['status'] == 'answered'
        assert step.request['responded_via'] == 'web'

    def test_loose_events_and_quiet_events(self) -> None:
        """A fill outside any turn is shown on its own, and a quiet event outside a turn is not."""
        events = _Events()
        transcript = chat_transcript.ChatTranscript()
        transcript.add(
            events.make(
                'fill', status='COMPLETE', filled_quantity=10, average_price=5.0
            )
        )
        transcript.add(events.make('account_status', total_balance=100.0))

        assert len(transcript.items) == 1
        assert isinstance(transcript.items[0], chat_items.LooseEvent)

    def test_an_event_seen_twice_is_added_once(self) -> None:
        """An event read from the journal and received live is added only once."""
        events = _Events()
        transcript = chat_transcript.ChatTranscript()
        trigger = events.make(
            'trigger_received', trigger_id='t1', source='user_message'
        )
        transcript.add(trigger)

        assert transcript.add(dict(trigger)) is None
        assert len(transcript.items) == 1
