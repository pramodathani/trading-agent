"""The pieces of a chat: turns, the steps inside them, and events that belong to no turn.

They mirror the web page's chatTurnBuilder.ts types, and ChatTranscript fills them in from gateway events.

Typical usage example:

  turn = ChatTurn(trigger_id='t1', source='user_message', text='Hello')
  turn.status_text()  # 'waiting in the queue'
"""

import dataclasses
import json
from typing import Any


@dataclasses.dataclass
class ToolStep:
    """One tool call inside a turn, with its result once it arrives.

    Attributes:
        call_id: The call's id, which its result carries too.
        name: The tool's name.
        arguments: The call's arguments.
        result_text: The tool's answer, or None while it runs.
        is_error: Whether the tool reported a failure.
        picture_path: A picture the tool showed the model, relative to the trader folder, or None.
        ended_early: Whether the turn ended, for example by a stop, before the tool answered.
    """

    call_id: str
    name: str
    arguments: dict[str, Any]
    result_text: str | None = None
    is_error: bool = False
    picture_path: str | None = None
    ended_early: bool = False

    def arguments_text(self) -> str:
        """The arguments as indented JSON.

        Returns:
            str: The JSON text.
        """
        return json.dumps(self.arguments, indent=2, ensure_ascii=False)


@dataclasses.dataclass
class EventStep:
    """Any other event shown inside a turn, such as a risk decision or a model switch.

    Attributes:
        event: The event, with kind, trader, payload and created_at.
    """

    event: dict[str, Any]


@dataclasses.dataclass
class SteeringStep:
    """A message the user sent while the turn was running, at the point it arrived.

    Attributes:
        message: The message's own turn, which says whether it reached the running turn.
    """

    message: ChatTurn


@dataclasses.dataclass
class RequestStep:
    """A question, plan or permission request the trader made during a turn, with its latest status.

    Attributes:
        request: The request, as GET /api/requests returns it.
    """

    request: dict[str, Any]


@dataclasses.dataclass
class ToolRun:
    """Tool calls in a row, shown as one folded line.

    Attributes:
        steps: The tool calls, in order.
    """

    steps: list[ToolStep]


@dataclasses.dataclass
class ChatTurn:
    """One trigger and everything the trader did about it.

    Attributes:
        trigger_id: The trigger's id.
        source: What woke the trader, such as "user_message" or "cron".
        text: The trigger's text.
        attachments: The files the user sent with it.
        received_at: When the gateway received it, as ISO text.
        started_at: When the turn started, or None.
        finished_at: When the turn finished, or None.
        started: Whether the turn has started.
        finished: Whether the turn has finished.
        steps: Tool calls, events, steering messages and requests, in order.
        answer: The trader's final answer, or None until it arrives.
        silent: Whether the trader decided there was nothing to say.
        error: Why the turn failed, or None.
        backend: The backend that answered, or None.
        steering_into: The running turn this message was handed to, or None.
        steering_outcome: "waiting", "delivered" or "queued" for a steering message, otherwise None.
        stopped: Whether the user stopped the turn.
        request_id: The question, plan or permission this trigger answers, or None.
        streaming_text: The text the trader is writing now, before the final answer arrives.
    """

    trigger_id: str
    source: str
    text: str
    attachments: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    received_at: str = ''
    started_at: str | None = None
    finished_at: str | None = None
    started: bool = False
    finished: bool = False
    steps: list[ToolStep | EventStep | SteeringStep | RequestStep] = (
        dataclasses.field(default_factory=list)
    )
    answer: str | None = None
    silent: bool = False
    error: str | None = None
    backend: str | None = None
    steering_into: str | None = None
    steering_outcome: str | None = None
    stopped: bool = False
    request_id: str | None = None
    streaming_text: str = ''

    def status_text(self) -> str:
        """Where the turn has got to, in the web page's words.

        Returns:
            str: A short status line, such as "answered by claude" or "waiting in the queue".
        """
        if self.stopped:
            return 'stopped by you'
        if self.finished:
            if self.backend is not None:
                return f'answered by {self.backend}'
            return 'finished'
        if self.started:
            return 'working…'
        if self.steering_outcome == 'waiting':
            return 'waiting for the running turn to pick it up at its next tool call'
        if self.steering_outcome == 'delivered':
            return 'handed to the running turn'
        if self.steering_outcome == 'queued':
            return 'the running turn ended first, so this is the next turn'
        return 'waiting in the queue'

    def running_tool(self) -> ToolStep | None:
        """The tool call still waiting for its result, if any.

        Returns:
            ToolStep | None: The newest tool call when it has no result yet, otherwise None.
        """
        for step in reversed(self.steps):
            if isinstance(step, ToolStep):
                if step.result_text is None and not step.ended_early:
                    return step
                return None
        return None

    def segments(
        self,
    ) -> list[ToolRun | EventStep | SteeringStep | RequestStep]:
        """The steps, with tool calls in a row grouped into one run.

        Returns:
            list[ToolRun | EventStep | SteeringStep | RequestStep]: The segments, in order.
        """
        segments = []
        for step in self.steps:
            if isinstance(step, ToolStep):
                if segments and isinstance(segments[-1], ToolRun):
                    segments[-1].steps.append(step)
                else:
                    segments.append(ToolRun(steps=[step]))
            else:
                segments.append(step)
        return segments


@dataclasses.dataclass
class LooseEvent:
    """An event that belongs to no turn, such as a fill reported while the trader was idle.

    Attributes:
        event: The event.
    """

    event: dict[str, Any]
