"""A question, plan or permission request the trader made during a turn, with its answer once given.

The request itself is answered in the request dock above the message box; this line records it in the transcript.

Typical usage example:

  view = RequestStepView(step)
  view.show(step)
"""

import json
from typing import Any

from textual import widgets
from textual.content import Content

from trading_agent.terminal import chat_items
from trading_agent.terminal import event_describer

_MOST_RESULT_CHARACTERS = 400


class RequestStepView(widgets.Static):
    """The request and what became of it."""

    def __init__(self, step: chat_items.RequestStep):
        """Creates the view.

        Args:
            step (chat_items.RequestStep): The request step.
        """
        super().__init__(self._content(step.request), classes='request-step')

    def show(self, step: chat_items.RequestStep) -> None:
        """Updates the view.

        Args:
            step (chat_items.RequestStep): The request step, perhaps now answered.
        """
        self.update(self._content(step.request))

    def _content(self, request: dict[str, Any]) -> Content:
        """The view's text.

        Args:
            request (dict[str, Any]): The request.

        Returns:
            Content: What the trader asked for, and the answer or the waiting state.
        """
        description = event_describer.EventDescriber().describe(
            {
                'kind': 'user_request',
                'payload': request,
            }
        )
        title = description.title
        if description.detail:
            title = f'{title}: {description.detail}'
        return Content.from_markup(
            '◆ [b]$title[/b]\n[dim]$outcome[/dim]',
            title=title,
            outcome=self._outcome(request),
        )

    def _outcome(self, request: dict[str, Any]) -> str:
        """What became of the request, in words.

        Args:
            request (dict[str, Any]): The request.

        Returns:
            str: Such as "Waiting for you, in the dock below" or "You chose: Yes, via web".
        """
        status = request.get('status')
        if status == 'pending':
            return 'Waiting for you, in the dock below.'
        if status == 'expired':
            return 'Lapsed without an answer.'
        if status == 'dismissed':
            return 'Dismissed.'
        response = request.get('response')
        if not isinstance(response, dict):
            response = {}
        via = request.get('responded_via')
        via_text = ''
        if via:
            via_text = f', via {via}'
        kind = request.get('kind')
        if kind == 'permission':
            return self._permission_outcome(response) + via_text
        if kind == 'plan':
            decision = 'Approved'
            if response.get('decision') == 'revise':
                decision = 'Sent back to keep planning'
            feedback = response.get('feedback')
            if feedback:
                decision += f': {feedback}'
            return decision + via_text
        return self._answers_text(response) + via_text

    def _permission_outcome(self, response: dict[str, Any]) -> str:
        """A permission decision and the call's result.

        Args:
            response (dict[str, Any]): The response.

        Returns:
            str: Such as "Allowed once. Result: ...".
        """
        words = {
            'allow_once': 'Allowed once',
            'always_allow': 'Always allowed',
            'deny': 'Denied',
        }
        decision = str(response.get('decision', ''))
        text = words.get(decision, decision)
        if response.get('reason'):
            text += f' ({response["reason"]})'
        result = response.get('result')
        if result:
            result_text = str(result)
            if len(result_text) > _MOST_RESULT_CHARACTERS:
                result_text = result_text[:_MOST_RESULT_CHARACTERS] + '…'
            text += f'. Result: {result_text}'
        return text

    def _answers_text(self, response: dict[str, Any]) -> str:
        """The answers to the trader's questions.

        Args:
            response (dict[str, Any]): The response.

        Returns:
            str: Each answer's chosen labels and other text.
        """
        answers = response.get('answers')
        if not isinstance(answers, list):
            return f'Answered: {json.dumps(response, ensure_ascii=False)}'
        parts = []
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            chosen = []
            for label in answer.get('selected') or []:
                chosen.append(str(label))
            if answer.get('other'):
                chosen.append(str(answer['other']))
            parts.append(', '.join(chosen))
        return 'You chose: ' + '; '.join(parts)
