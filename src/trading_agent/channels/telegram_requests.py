"""The desks' questions and plans on Telegram, answered with buttons.

Each question becomes one message with a button per option. A single-choice question is settled by one press; a multiple-choice one ticks options and is settled with Done. "Other…" and a plan's "Keep planning" ask the user to type a reply, and the chat's next message is taken as that reply instead of going to the desk. Once every question of a request is settled, the answers go to the desk through the same responder the web page uses.

When a request is answered anywhere, on the web page or in another chat, its Telegram messages lose their buttons and say how it was settled.

Typical usage example:

  requests = TelegramRequests(api, pairing, store, responder)
  await requests.show(request)
  await requests.press(chat, button)
"""

import datetime
import json
import logging
from collections.abc import Callable
from typing import Any

from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.channels import telegram_api as telegram_api_module
from trading_agent.requests import user_request as user_request_module
from trading_agent.requests import user_request_responder as user_request_responder_module
from trading_agent.requests import user_request_store as user_request_store_module

_LOGGER = logging.getLogger(__name__)
_VIA = 'telegram'
_PICK = 'pick'
_OTHER = 'other'
_DONE = 'done'
_DISMISS = 'dismiss'
_APPROVE = 'approve'
_REVISE = 'revise'
_FEEDBACK = 'feedback'
_ALLOW_ONCE = 'allow'
_ALWAYS_ALLOW = 'always'
_DENY = 'deny'
_PERMISSION_DECISIONS = {
    _ALLOW_ONCE: 'allow_once',
    _ALWAYS_ALLOW: 'always_allow',
    _DENY: 'deny',
}
_SEPARATOR = '|'
_INDIA = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


class TelegramRequests:
    """Shows requests in the paired chats, and turns button presses and typed replies into answers.

    Each request's progress is kept in memory while it is open: the answers chosen so far, which questions are settled, and which messages hold its buttons. After a restart, the request is shown again when it is next published.
    """

    def __init__(
        self,
        api: telegram_api_module.TelegramApi,
        pairing: pairing_store_module.PairingStore,
        store: user_request_store_module.UserRequestStore,
        responder: user_request_responder_module.UserRequestResponder,
    ):
        """Creates the handler.

        Args:
            api (telegram_api_module.TelegramApi): The connection to Telegram.
            pairing (pairing_store_module.PairingStore): The paired chats.
            store (user_request_store_module.UserRequestStore): Where requests are kept.
            responder (user_request_responder_module.UserRequestResponder): Records the answers and tells the desks.
        """
        self._api = api
        self._pairing = pairing
        self._store = store
        self._responder = responder
        self._drafts: dict[str, list[dict[str, Any]]] = {}
        self._settled: dict[str, set[int]] = {}
        self._messages: dict[str, list[tuple[int, int, int]]] = {}
        self._awaiting_text: dict[int, tuple[str, str, int]] = {}

    async def show(self, request: user_request_module.UserRequest) -> None:
        """Sends a request to every paired chat, with its buttons.

        Args:
            request (user_request_module.UserRequest): The request.
        """
        if request.kind == user_request_module.QUESTION:
            questions = request.content['questions']
            self._drafts[request.request_id] = []
            for _ in questions:
                self._drafts[request.request_id].append(
                    {
                        'selected': [],
                        'other': '',
                    }
                )
            self._settled[request.request_id] = set()
            for chat in self._pairing.paired_chats():
                for index in range(len(questions)):
                    await self._send(
                        request,
                        chat.chat_id,
                        index,
                        self._question_text(request, index),
                        self._question_buttons(request, index),
                    )
            return
        if request.kind == user_request_module.PERMISSION:
            for chat in self._pairing.paired_chats():
                await self._send(
                    request,
                    chat.chat_id,
                    -1,
                    self._permission_text(request),
                    self._permission_buttons(request),
                )
            return
        if request.kind == user_request_module.PLAN:
            text = f'📋 {request.desk} presents a plan for your approval: {request.content["title"]}\n\n{request.content["plan"]}\n\nApprove it, or ask for changes?'
            for chat in self._pairing.paired_chats():
                await self._send(
                    request,
                    chat.chat_id,
                    -1,
                    text,
                    self._plan_buttons(request),
                )

    def wants_text(self, chat_id: int) -> bool:
        """Says whether the chat's next message is a typed reply to a request.

        Args:
            chat_id (int): The chat.

        Returns:
            bool: True after "Other…" or "Keep planning" was pressed in that chat.
        """
        return chat_id in self._awaiting_text

    async def receive_text(self, chat_id: int, text: str) -> None:
        """Takes a typed reply as the "Other" answer or as plan feedback.

        Args:
            chat_id (int): The chat.
            text (str): The reply.
        """
        request_id, purpose, index = self._awaiting_text.pop(chat_id)
        if not text.strip():
            return
        if purpose == _FEEDBACK:
            await self._respond(
                chat_id,
                lambda: self._responder.decide_plan(request_id, 'revise', text, _VIA),
            )
            return
        drafts = self._drafts.get(request_id)
        if drafts is None:
            await self._note(chat_id, 'That question is no longer open.')
            return
        request = self._store.get(request_id)
        question = request.content['questions'][index]
        if not question.get('multi_select'):
            drafts[index]['selected'] = []
        drafts[index]['other'] = text.strip()
        await self._settle(request, index, chat_id)

    async def press(
        self,
        button: telegram_api_module.IncomingButton,
    ) -> None:
        """Handles a press on one of a request's buttons.

        Args:
            button (telegram_api_module.IncomingButton): The press.
        """
        parts = button.data.split(_SEPARATOR)
        if len(parts) != 4:
            await self._acknowledge(button, '')
            return
        action, request_id, question_text, option_text = parts
        index = int(question_text)
        option = int(option_text)
        try:
            request = self._store.pending_request(request_id)
        except user_request_store_module.UserRequestError as error:
            await self._acknowledge(button, str(error))
            return
        if action in _PERMISSION_DECISIONS:
            await self._acknowledge(button, '')
            try:
                await self._responder.decide_permission(
                    request_id,
                    _PERMISSION_DECISIONS[action],
                    '',
                    _VIA,
                )
            except ValueError as error:
                await self._note(button.chat_id, f'Not done: {error}')
        elif action == _DISMISS:
            await self._acknowledge(button, 'Dismissed')
            await self._respond(
                button.chat_id,
                lambda: self._responder.dismiss(request_id, _VIA),
            )
        elif action == _APPROVE:
            await self._acknowledge(button, 'Approved')
            await self._respond(
                button.chat_id,
                lambda: self._responder.decide_plan(request_id, 'approve', '', _VIA),
            )
        elif action == _REVISE:
            self._awaiting_text[button.chat_id] = (request_id, _FEEDBACK, -1)
            await self._acknowledge(button, '')
            await self._note(button.chat_id, 'Type what should change in the plan and send it.')
        elif action == _OTHER:
            self._awaiting_text[button.chat_id] = (request_id, _OTHER, index)
            await self._acknowledge(button, '')
            question = request.content['questions'][index]['question']
            await self._note(button.chat_id, f'Type your own answer to "{question}" and send it.')
        elif action == _PICK:
            await self._pick(request, index, option, button)
        elif action == _DONE:
            drafts = self._drafts.get(request_id, [])
            if index >= len(drafts) or not (drafts[index]['selected'] or drafts[index]['other']):
                await self._acknowledge(button, 'Choose at least one first')
                return
            await self._acknowledge(button, '')
            await self._settle(request, index, button.chat_id)

    async def close(self, payload: dict[str, Any]) -> None:
        """Removes a request's buttons once it is answered anywhere, saying how it was settled.

        Args:
            payload (dict[str, Any]): The user_response event's payload.
        """
        request_id = str(payload.get('request_id', ''))
        sent = self._messages.pop(request_id, [])
        self._drafts.pop(request_id, None)
        self._settled.pop(request_id, None)
        for chat_id in list(self._awaiting_text):
            if self._awaiting_text[chat_id][0] == request_id:
                self._awaiting_text.pop(chat_id)
        if not sent:
            return
        request = self._store.get(request_id)
        outcome = self._outcome(request)
        for chat_id, message_id, index in sent:
            if index >= 0:
                text = f'{self._question_text(request, index)}\n\n{outcome}'
            elif request.kind == user_request_module.PERMISSION:
                text = f'{self._permission_text(request)}\n\n{outcome}'
            else:
                text = f'📋 {request.content.get("title", "Plan")}\n\n{outcome}'
            try:
                await self._api.edit(chat_id, message_id, text, None)
            except telegram_api_module.TelegramApiError as error:
                _LOGGER.warning('Could not update a Telegram request message: %s', error)

    async def _pick(
        self,
        request: user_request_module.UserRequest,
        index: int,
        option: int,
        button: telegram_api_module.IncomingButton,
    ) -> None:
        """Chooses an option: settles a single-choice question, or ticks one of a multiple-choice question.

        Args:
            request (user_request_module.UserRequest): The question request.
            index (int): The question's position.
            option (int): The option's position.
            button (telegram_api_module.IncomingButton): The press.
        """
        question = request.content['questions'][index]
        label = question['options'][option]['label']
        drafts = self._drafts.setdefault(request.request_id, [])
        while len(drafts) <= index:
            drafts.append(
                {
                    'selected': [],
                    'other': '',
                }
            )
        if not question.get('multi_select'):
            drafts[index] = {
                'selected': [
                    label,
                ],
                'other': '',
            }
            await self._acknowledge(button, label)
            await self._settle(request, index, button.chat_id)
            return
        chosen = drafts[index]['selected']
        if label in chosen:
            chosen.remove(label)
        else:
            chosen.append(label)
        await self._acknowledge(button, '')
        try:
            await self._api.edit(
                button.chat_id,
                button.message_id,
                self._question_text(request, index),
                self._question_buttons(request, index),
            )
        except telegram_api_module.TelegramApiError as error:
            _LOGGER.warning('Could not update a Telegram question: %s', error)

    async def _settle(
        self,
        request: user_request_module.UserRequest,
        index: int,
        chat_id: int,
    ) -> None:
        """Marks one question as answered, and sends every answer once all are.

        Args:
            request (user_request_module.UserRequest): The question request.
            index (int): The question's position.
            chat_id (int): The chat that answered, for any error message.
        """
        settled = self._settled.setdefault(request.request_id, set())
        settled.add(index)
        for chat, message_id, question_index in self._messages.get(request.request_id, []):
            if question_index == index:
                answer = self._answer_words(self._drafts[request.request_id][index])
                try:
                    await self._api.edit(
                        chat,
                        message_id,
                        f'{self._question_text(request, index)}\n\n✓ {answer}',
                        None,
                    )
                except telegram_api_module.TelegramApiError as error:
                    _LOGGER.warning('Could not update a Telegram question: %s', error)
        if len(settled) < len(request.content['questions']):
            return
        drafts = self._drafts[request.request_id]
        await self._respond(
            chat_id,
            lambda: self._responder.answer_question(request.request_id, drafts, _VIA),
        )

    async def _respond(
        self,
        chat_id: int,
        action: Callable[[], user_request_module.UserRequest],
    ) -> None:
        """Runs a response, telling the chat when it is refused.

        Args:
            chat_id (int): The chat that responded.
            action (Callable[[], user_request_module.UserRequest]): The response.
        """
        try:
            action()
        except ValueError as error:
            await self._note(chat_id, f'Not sent: {error}')

    async def _send(
        self,
        request: user_request_module.UserRequest,
        chat_id: int,
        index: int,
        text: str,
        rows: telegram_api_module.ButtonRows,
    ) -> None:
        """Sends one message with buttons and remembers it, logging a failure instead of raising it.

        Args:
            request (user_request_module.UserRequest): The request.
            chat_id (int): The chat.
            index (int): The question's position, or -1 for a plan.
            text (str): The message.
            rows (telegram_api_module.ButtonRows): The buttons.
        """
        try:
            message_id = await self._api.send_with_buttons(chat_id, text, rows)
        except telegram_api_module.TelegramApiError as error:
            _LOGGER.warning('Could not send a request to Telegram chat %s: %s', chat_id, error)
            return
        self._messages.setdefault(request.request_id, []).append(
            (chat_id, message_id, index)
        )

    async def _note(self, chat_id: int, text: str) -> None:
        """Sends a short message, logging a failure instead of raising it.

        Args:
            chat_id (int): The chat.
            text (str): The message.
        """
        try:
            await self._api.send(chat_id, text)
        except telegram_api_module.TelegramApiError as error:
            _LOGGER.warning('Could not send to Telegram chat %s: %s', chat_id, error)

    async def _acknowledge(
        self,
        button: telegram_api_module.IncomingButton,
        text: str,
    ) -> None:
        """Acknowledges a press, logging a failure instead of raising it.

        Args:
            button (telegram_api_module.IncomingButton): The press.
            text (str): A short note shown on the phone, or empty.
        """
        try:
            await self._api.acknowledge(button.callback_id, text)
        except telegram_api_module.TelegramApiError as error:
            _LOGGER.warning('Could not acknowledge a Telegram button: %s', error)

    def _question_text(
        self,
        request: user_request_module.UserRequest,
        index: int,
    ) -> str:
        """The text of one question's message: the question, the options with their descriptions, and any previews.

        Args:
            request (user_request_module.UserRequest): The request.
            index (int): The question's position.

        Returns:
            str: The message.
        """
        questions = request.content['questions']
        question = questions[index]
        counter = f' ({index + 1}/{len(questions)})' if len(questions) > 1 else ''
        lines = [
            f'❓ {request.desk} asks{counter} · {question["header"]}',
            '',
            question['question'],
            '',
        ]
        for position, option in enumerate(question['options'], start=1):
            lines.append(f'{position}. {option["label"]}: {option["description"]}')
        for position, option in enumerate(question['options'], start=1):
            if option.get('preview'):
                lines.append('')
                lines.append(f'Preview of {position}:')
                lines.append(option['preview'])
        if question.get('multi_select'):
            lines.append('')
            lines.append('Choose all that apply, then press Done.')
        return '\n'.join(lines)

    def _question_buttons(
        self,
        request: user_request_module.UserRequest,
        index: int,
    ) -> list[list[tuple[str, str]]]:
        """The buttons of one question: one per option, then Other, Done for multiple choice, and Dismiss.

        Args:
            request (user_request_module.UserRequest): The request.
            index (int): The question's position.

        Returns:
            list[list[tuple[str, str]]]: The rows of (label, data) pairs.
        """
        question = request.content['questions'][index]
        chosen = []
        drafts = self._drafts.get(request.request_id, [])
        if index < len(drafts):
            chosen = drafts[index]['selected']
        rows = []
        for position, option in enumerate(question['options']):
            label = f'{position + 1}. {option["label"]}'
            if question.get('multi_select'):
                mark = '☑' if option['label'] in chosen else '☐'
                label = f'{mark} {label}'
            rows.append(
                [
                    (label, self._data(_PICK, request.request_id, index, position)),
                ]
            )
        last_row = [
            ('Other…', self._data(_OTHER, request.request_id, index, 0)),
        ]
        if question.get('multi_select'):
            last_row.append(('Done', self._data(_DONE, request.request_id, index, 0)))
        rows.append(last_row)
        rows.append(
            [
                ('Dismiss', self._data(_DISMISS, request.request_id, index, 0)),
            ]
        )
        return rows

    def _permission_text(self, request: user_request_module.UserRequest) -> str:
        """The text of a permission request: the tool, its arguments, and when it lapses.

        Args:
            request (user_request_module.UserRequest): The permission request.

        Returns:
            str: The message.
        """
        arguments = json.dumps(request.content.get('arguments') or {}, indent=2, ensure_ascii=False)
        lines = [
            f'🔐 {request.desk} wants to run {request.content["tool_name"]}',
            '',
            arguments,
        ]
        if request.expires_at is not None:
            lapse = datetime.datetime.fromisoformat(request.expires_at).astimezone(_INDIA)
            lines.append('')
            lines.append(f'Lapses at {lapse:%H:%M} India time if you do not answer.')
        return '\n'.join(lines)

    def _permission_buttons(
        self,
        request: user_request_module.UserRequest,
    ) -> list[list[tuple[str, str]]]:
        """The buttons of a permission request: Allow once, Always allow, and Deny.

        Args:
            request (user_request_module.UserRequest): The permission request.

        Returns:
            list[list[tuple[str, str]]]: The rows of (label, data) pairs.
        """
        tool_name = request.content['tool_name']
        return [
            [
                ('✅ Allow once', self._data(_ALLOW_ONCE, request.request_id, -1, 0)),
            ],
            [
                (f'Always allow {tool_name}', self._data(_ALWAYS_ALLOW, request.request_id, -1, 0)),
            ],
            [
                ('⛔ Deny', self._data(_DENY, request.request_id, -1, 0)),
            ],
        ]

    def _plan_buttons(
        self,
        request: user_request_module.UserRequest,
    ) -> list[list[tuple[str, str]]]:
        """The buttons of a plan: Approve, Keep planning, and Dismiss.

        Args:
            request (user_request_module.UserRequest): The plan request.

        Returns:
            list[list[tuple[str, str]]]: The rows of (label, data) pairs.
        """
        return [
            [
                ('✅ Approve', self._data(_APPROVE, request.request_id, -1, 0)),
                ('✏️ Keep planning', self._data(_REVISE, request.request_id, -1, 0)),
            ],
            [
                ('Dismiss', self._data(_DISMISS, request.request_id, -1, 0)),
            ],
        ]

    def _outcome(self, request: user_request_module.UserRequest) -> str:
        """How a finished request was settled, in words.

        Args:
            request (user_request_module.UserRequest): The finished request.

        Returns:
            str: Such as "✓ Answered on the web: 2%".
        """
        place = 'on Telegram'
        if request.responded_via == 'web':
            place = 'on the web'
        elif request.responded_via == 'terminal':
            place = 'in the terminal'
        if request.status == user_request_module.DISMISSED:
            return f'Dismissed {place}.'
        if request.status == user_request_module.EXPIRED:
            return 'Expired.'
        response = request.response or {}
        if request.kind == user_request_module.PERMISSION:
            if response.get('decision') == 'deny':
                return f'⛔ Denied {place}.'
            always = ' and allowed from now on' if response.get('decision') == 'always_allow' else ''
            return f'✅ Allowed {place}{always}. Result: {str(response.get("result", ""))[:500]}'
        if request.kind == user_request_module.PLAN:
            if response.get('decision') == 'approve':
                return f'✓ Approved {place}.'
            return f'✏️ Changes asked for {place}: {response.get("feedback", "")}'
        answers = []
        for answer in response.get('answers', []):
            answers.append(self._answer_words(answer))
        return f'✓ Answered {place}: {"; ".join(answers)}'

    @staticmethod
    def _answer_words(answer: dict[str, Any]) -> str:
        """One answer in words.

        Args:
            answer (dict[str, Any]): The chosen labels and the Other text.

        Returns:
            str: The labels, with the Other text in quotes.
        """
        parts = list(answer.get('selected') or [])
        if answer.get('other'):
            parts.append(f'"{answer["other"]}"')
        return ', '.join(parts)

    @staticmethod
    def _data(action: str, request_id: str, index: int, option: int) -> str:
        """The text attached to a button, which comes back when it is pressed.

        Args:
            action (str): What the button does.
            request_id (str): The request.
            index (int): The question's position, or -1.
            option (int): The option's position, or 0.

        Returns:
            str: Such as "pick|20261018-...|0|2", well under Telegram's 64-byte limit.
        """
        return _SEPARATOR.join(
            [
                action,
                request_id,
                str(index),
                str(option),
            ]
        )
