"""The user's answers to a trader's questions: checked against the options, and written up for the trader.

Typical usage example:

  response = QuestionResponse(request, [{'selected': ['Wait'], 'other': ''}])
  response.check()
  text = response.message()
"""

from collections.abc import Sequence
from typing import Any

from trading_agent.requests import user_request as user_request_module


class QuestionResponse:
    """One answer per question: the options chosen, and any text typed under "Other"."""

    def __init__(
        self,
        request: user_request_module.UserRequest,
        answers: Sequence[dict[str, Any]],
    ):
        """Creates the response.

        Args:
            request (user_request_module.UserRequest): The question request.
            answers (Sequence[dict[str, Any]]): One {"selected": [labels], "other": text} per question, in order.
        """
        self._request = request
        self._answers = list(answers)

    def check(self) -> None:
        """Checks that each answer fits its question.

        Raises:
            ValueError: The number of answers is wrong, an answer names an option the question does not have, a single-choice question has more or fewer than one answer, or a multiple-choice question has none.
        """
        questions = self._request.content['questions']
        if len(self._answers) != len(questions):
            raise ValueError(
                f'Expected {len(questions)} answers, got {len(self._answers)}'
            )
        for question, answer in zip(questions, self._answers):
            labels = []
            for option in question['options']:
                labels.append(option['label'])
            selected = list(answer.get('selected') or [])
            for label in selected:
                if label not in labels:
                    raise ValueError(
                        f'{label!r} is not an option of {question["question"]!r}'
                    )
            chosen = len(selected)
            if str(answer.get('other') or '').strip():
                chosen += 1
            if question.get('multi_select'):
                if chosen == 0:
                    raise ValueError(
                        f'Choose at least one answer to {question["question"]!r}'
                    )
            elif chosen != 1:
                raise ValueError(
                    f'Choose exactly one answer to {question["question"]!r}'
                )

    def stored(self) -> dict[str, Any]:
        """The response as saved with the request.

        Returns:
            dict[str, Any]: The answers, cleaned.
        """
        answers = []
        for answer in self._answers:
            answers.append(
                {
                    'selected': list(answer.get('selected') or []),
                    'other': str(answer.get('other') or '').strip(),
                }
            )
        return {
            'answers': answers,
        }

    def message(self) -> str:
        """The message the trader receives.

        Returns:
            str: Each question with the user's answer.
        """
        questions = self._request.content['questions']
        lines = [
            f'The user answered your question{"s" if len(questions) > 1 else ""} (request {self._request.request_id}):',
        ]
        for index, question in enumerate(questions):
            answer = self.stored()['answers'][index]
            chosen = []
            for label in answer['selected']:
                chosen.append(f'"{label}"')
            if answer['other']:
                chosen.append(f'their own answer: "{answer["other"]}"')
            lines.append(f'{index + 1}. {question["question"]}')
            lines.append(f'   Answer: {", ".join(chosen)}')
        return '\n'.join(lines)
