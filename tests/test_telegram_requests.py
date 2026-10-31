"""Tests for answering the traders' questions and plans with Telegram's buttons, on a stand-in for Telegram."""

import asyncio
from pathlib import Path

from tests import test_user_requests
from trading_agent.channels import pairing_store as pairing_store_module
from trading_agent.channels import telegram_api
from trading_agent.channels import telegram_requests
from trading_agent.requests import user_request as user_request_module

_OWNER = 111


class _StandInApi:
    """Records what the bot sends and edits, instead of reaching Telegram.

    Attributes:
        sent: Each message with buttons, as (chat_id, message_id, text, rows).
        edits: Each edit, as (chat_id, message_id, text, rows).
        notes: Each plain message, as (chat_id, text).
        acknowledged: The notes shown for button presses.
    """

    def __init__(self):
        """Creates the stand-in."""
        self.sent = []
        self.edits = []
        self.notes = []
        self.acknowledged = []

    async def send_with_buttons(self, chat_id: int, text: str, rows) -> int:
        """Records a message with buttons.

        Args:
            chat_id (int): The chat.
            text (str): The message.
            rows (telegram_api.ButtonRows): The buttons.

        Returns:
            int: A new message id.
        """
        message_id = len(self.sent) + 1
        self.sent.append((chat_id, message_id, text, rows))
        return message_id

    async def edit(
        self, chat_id: int, message_id: int, text: str, rows
    ) -> None:
        """Records an edit.

        Args:
            chat_id (int): The chat.
            message_id (int): The message.
            text (str): The new text.
            rows (telegram_api.ButtonRows | None): The new buttons, or None.
        """
        self.edits.append((chat_id, message_id, text, rows))

    async def send(self, chat_id: int, text: str) -> None:
        """Records a plain message.

        Args:
            chat_id (int): The chat.
            text (str): The message.
        """
        self.notes.append((chat_id, text))

    async def acknowledge(self, callback_id: str, text: str = '') -> None:
        """Records a press's note.

        Args:
            callback_id (str): The press.
            text (str): The note.
        """
        del callback_id
        self.acknowledged.append(text)


class _Telegram:
    """The request setup from the web tests, plus a paired chat and the Telegram handler.

    Attributes:
        setup: The store, responder, tools and stand-in trader.
        api: The stand-in Telegram.
        handler: The Telegram request handler.
    """

    def __init__(self, directory: Path):
        """Builds everything with the owner's chat paired.

        Args:
            directory (Path): A scratch folder.
        """
        self.setup = test_user_requests._Setup(directory)
        pairing = pairing_store_module.PairingStore(
            directory / 'telegram_pairing.json'
        )
        pairing.approve(pairing.request(_OWNER, 'Owner'), 'main')
        self.api = _StandInApi()
        self.handler = telegram_requests.TelegramRequests(
            self.api,
            pairing,
            self.setup.store,
            self.setup.responder,
        )

    def button(
        self, message_index: int, label_start: str
    ) -> telegram_api.IncomingButton:
        """Builds a press on the button whose label starts with some text.

        Args:
            message_index (int): Which sent message holds the button, in sending order.
            label_start (str): The start of the button's label.

        Returns:
            telegram_api.IncomingButton: The press.
        """
        _, message_id, _, rows = self.api.sent[message_index]
        for row in rows:
            for label, data in row:
                if label.startswith(label_start):
                    return telegram_api.IncomingButton(
                        chat_id=_OWNER,
                        sender_name='Owner',
                        callback_id='press',
                        data=data,
                        message_id=message_id,
                    )
        raise AssertionError(f'No button starting with {label_start!r}')

    def press(self, message_index: int, label_start: str) -> None:
        """Presses a button.

        Args:
            message_index (int): Which sent message holds the button.
            label_start (str): The start of the button's label.
        """
        asyncio.run(self.handler.press(self.button(message_index, label_start)))

    def answered_payload(self, request_id: str) -> dict:
        """The payload of the user_response event a finished request publishes.

        Args:
            request_id (str): The request.

        Returns:
            dict: The payload.
        """
        return {
            'request_id': request_id,
        }


class TestTelegramRequests:
    """Tests for TelegramRequests."""

    def test_question_is_sent_with_a_button_per_option(
        self, tmp_path: Path
    ) -> None:
        """A question goes to the paired chat with its options, Other and Dismiss as buttons, and its preview in the text."""
        telegram = _Telegram(tmp_path)
        request = telegram.setup.ask()

        asyncio.run(telegram.handler.show(request))

        chat_id, _, text, rows = telegram.api.sent[0]
        labels = [label for row in rows for label, _ in row]
        assert chat_id == _OWNER
        assert 'Which stop loss should the trader use?' in text
        assert 'Preview of 2:' in text
        assert labels == [
            '1. 1% (Recommended)',
            '2. 2%',
            'Other…',
            'Dismiss',
        ]

    def test_one_press_answers_a_single_choice_question(
        self, tmp_path: Path
    ) -> None:
        """Pressing an option answers the request, tells the trader, and the buttons go once it is closed."""
        telegram = _Telegram(tmp_path)
        request = telegram.setup.ask()
        asyncio.run(telegram.handler.show(request))

        telegram.press(0, '2.')
        answered = telegram.setup.store.get(request.request_id)
        asyncio.run(
            telegram.handler.close(
                telegram.answered_payload(request.request_id)
            )
        )

        assert answered.status == user_request_module.ANSWERED
        assert answered.responded_via == 'telegram'
        assert answered.response['answers'][0]['selected'] == [
            '2%',
        ]
        assert '"2%"' in telegram.setup.trader.triggers[-1].text
        assert telegram.api.edits[-1][3] is None
        assert 'Answered on Telegram' in telegram.api.edits[-1][2]

    def test_multiple_choice_ticks_options_then_done(
        self, tmp_path: Path
    ) -> None:
        """Options are ticked one by one, and Done sends them."""
        telegram = _Telegram(tmp_path)
        request = telegram.setup.ask(multi_select=True)
        asyncio.run(telegram.handler.show(request))

        telegram.press(0, '☐ 1.')
        telegram.press(0, '☐ 2.')
        ticked_rows = telegram.api.edits[-1][3]
        telegram.press(0, 'Done')

        assert ticked_rows[0][0][0].startswith('☑')
        assert ticked_rows[1][0][0].startswith('☑')
        assert telegram.setup.store.get(request.request_id).response['answers'][
            0
        ]['selected'] == [
            '1% (Recommended)',
            '2%',
        ]

    def test_done_without_a_choice_is_refused(self, tmp_path: Path) -> None:
        """Done before ticking anything only shows a note."""
        telegram = _Telegram(tmp_path)
        request = telegram.setup.ask(multi_select=True)
        asyncio.run(telegram.handler.show(request))

        telegram.press(0, 'Done')

        assert telegram.api.acknowledged[-1] == 'Choose at least one first'
        assert (
            telegram.setup.store.get(request.request_id).status
            == user_request_module.PENDING
        )

    def test_other_takes_the_next_typed_message(self, tmp_path: Path) -> None:
        """After Other, the chat's next message is the answer, not a message to the trader."""
        telegram = _Telegram(tmp_path)
        request = telegram.setup.ask()
        asyncio.run(telegram.handler.show(request))

        telegram.press(0, 'Other')
        waiting = telegram.handler.wants_text(_OWNER)
        asyncio.run(telegram.handler.receive_text(_OWNER, 'Use 1.5%'))

        assert waiting
        assert not telegram.handler.wants_text(_OWNER)
        assert (
            telegram.setup.store.get(request.request_id).response['answers'][0][
                'other'
            ]
            == 'Use 1.5%'
        )

    def test_plan_is_approved_or_revised_with_typed_feedback(
        self, tmp_path: Path
    ) -> None:
        """Approve settles a plan at once; Keep planning takes the next message as feedback."""
        telegram = _Telegram(tmp_path)
        first = telegram.setup.plan()
        asyncio.run(telegram.handler.show(first))
        second = telegram.setup.plan()
        asyncio.run(telegram.handler.show(second))

        telegram.press(0, '✅ Approve')
        telegram.press(1, '✏️ Keep planning')
        asyncio.run(telegram.handler.receive_text(_OWNER, 'Smaller size'))

        assert (
            telegram.setup.store.get(first.request_id).response['decision']
            == 'approve'
        )
        assert telegram.setup.store.get(second.request_id).response == {
            'decision': 'revise',
            'feedback': 'Smaller size',
        }

    def test_press_on_an_answered_request_only_shows_a_note(
        self, tmp_path: Path
    ) -> None:
        """A request answered on the web cannot be answered again from Telegram."""
        telegram = _Telegram(tmp_path)
        request = telegram.setup.ask()
        asyncio.run(telegram.handler.show(request))
        telegram.setup.responder.dismiss(request.request_id, 'web')

        telegram.press(0, '1.')

        assert 'already dismissed' in telegram.api.acknowledged[-1]
        assert len(telegram.setup.trader.triggers) == 1
