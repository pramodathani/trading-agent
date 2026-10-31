"""The card for a trader's questions (ask_user), as the web page's QuestionCard.tsx shows them.

One to four questions, each with two to four options and an "Other" answer. With several questions there is one tab per question and a final tab to review and submit. A single question with a single choice is sent as soon as an option is picked.

Keys: Up and Down move, Enter or a number picks (a multiple-choice question ticks and unticks), the number after the last option goes to the Other box, Tab and Shift+Tab move between questions, Ctrl+S submits, Ctrl+X dismisses without answering.

Typical usage example:

  card = QuestionCard(request, gateway)
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import events
from textual import message
from textual import widgets
from textual import work
from textual.content import Content
from textual.widgets import option_list

from trading_agent.terminal import gateway_client


class QuestionCard(containers.Vertical):
    """A card for answering the trader's questions."""

    can_focus = True

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('tab', 'next_question', 'Next question', show=False),
        binding.Binding(
            'shift+tab', 'previous_question', 'Previous question', show=False
        ),
        binding.Binding('ctrl+s', 'submit', 'Submit', show=False),
        binding.Binding('ctrl+x', 'dismiss_request', 'Dismiss', show=False),
    ]

    class Done(message.Message):
        """The request was answered or dismissed."""

    def __init__(
        self,
        request: dict[str, Any],
        gateway: gateway_client.GatewayClient,
    ):
        """Creates the card.

        Args:
            request (dict[str, Any]): The pending question request.
            gateway (gateway_client.GatewayClient): The gateway, to send the answers.
        """
        super().__init__(classes='request-card question-card')
        self.request_id = request['request_id']
        self._request = request
        self._gateway = gateway
        content = request.get('content') or {}
        self._questions: list[dict[str, Any]] = list(
            content.get('questions') or []
        )
        self._drafts: list[dict[str, Any]] = []
        for _ in self._questions:
            self._drafts.append(
                {
                    'selected': [],
                    'other': '',
                }
            )
        self._tab = 0
        self._sending = False

    def compose(self):
        """Builds the card.

        Yields:
            Widget: The heading, tabs, question, options, Other box, preview, review, error and hint.
        """
        yield widgets.Static('', classes='request-heading')
        yield widgets.Static('', classes='question-tabs')
        yield widgets.Static('', classes='question-text')
        yield widgets.OptionList(classes='question-options')
        yield widgets.Input(
            placeholder='Other: type your own answer',
            classes='question-other',
            select_on_focus=False,
        )
        yield widgets.Markdown('', classes='question-preview')
        yield widgets.Static('', classes='question-review')
        yield widgets.Static('', classes='request-error')
        yield widgets.Static('', classes='request-hint')

    def on_mount(self) -> None:
        """Shows the first question."""
        self._show()

    def focus_card(self) -> None:
        """Puts the focus on the options, so the card's keys work."""
        if self._reviewing():
            self.focus()
            return
        self.query_one('.question-options', widgets.OptionList).focus()

    def on_key(self, event: events.Key) -> None:
        """Picks an option with its number key.

        Args:
            event (events.Key): The key press.
        """
        if isinstance(self.screen.focused, widgets.Input):
            return
        question = self._question()
        if question is None or not event.character:
            return
        if not event.character.isdigit():
            return
        number = int(event.character)
        options = question.get('options') or []
        if 1 <= number <= len(options):
            event.stop()
            self.query_one(
                '.question-options', widgets.OptionList
            ).highlighted = number - 1
            self._choose(options[number - 1]['label'])
        elif number == len(options) + 1:
            event.stop()
            self.query_one('.question-other', widgets.Input).focus()

    def on_option_list_option_highlighted(
        self, event: widgets.OptionList.OptionHighlighted
    ) -> None:
        """Shows the highlighted option's preview.

        Args:
            event (widgets.OptionList.OptionHighlighted): The highlight.
        """
        event.stop()
        self._show_preview(event.option_index)

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Picks the selected option.

        Args:
            event (widgets.OptionList.OptionSelected): The selection.
        """
        event.stop()
        question = self._question()
        if question is None:
            return
        self._choose(question['options'][event.option_index]['label'])

    def on_input_changed(self, event: widgets.Input.Changed) -> None:
        """Keeps the Other answer; for a single choice it replaces the picked option.

        Args:
            event (widgets.Input.Changed): The change.
        """
        event.stop()
        question = self._question()
        if question is None:
            return
        draft = self._drafts[self._tab]
        draft['other'] = event.value
        if event.value.strip() and not question.get('multi_select'):
            draft['selected'] = []
        self._show_options()
        self._show_tabs()

    def on_input_submitted(self, event: widgets.Input.Submitted) -> None:
        """Moves on, or submits, after an Other answer.

        Args:
            event (widgets.Input.Submitted): The submission.
        """
        event.stop()
        if not event.value.strip():
            return
        if len(self._questions) == 1:
            self.action_submit()
            return
        self.action_next_question()

    def action_next_question(self) -> None:
        """Shows the next question, or the review tab after the last."""
        if len(self._questions) < 2:
            return
        self._tab = min(self._tab + 1, len(self._questions))
        self._show()
        self.focus_card()

    def action_previous_question(self) -> None:
        """Shows the previous question."""
        if len(self._questions) < 2:
            return
        self._tab = max(self._tab - 1, 0)
        self._show()
        self.focus_card()

    def action_submit(self) -> None:
        """Sends the answers, when every question has one."""
        for index in range(len(self._questions)):
            if not self._is_answered(index):
                self._error('Answer every question first.')
                return
        self._send_answers()

    def action_dismiss_request(self) -> None:
        """Dismisses the questions without answering; the trader uses its own judgment."""
        self._dismiss()

    def _choose(self, label: str) -> None:
        """Picks or ticks an option.

        Args:
            label (str): The option's label.
        """
        question = self._question()
        if question is None:
            return
        draft = self._drafts[self._tab]
        if question.get('multi_select'):
            if label in draft['selected']:
                draft['selected'].remove(label)
            else:
                draft['selected'].append(label)
            self._show_options()
            self._show_tabs()
            return
        draft['selected'] = [
            label,
        ]
        draft['other'] = ''
        if len(self._questions) == 1:
            self._send_answers()
            return
        self.action_next_question()

    @work(exclusive=True, group='answer')
    async def _send_answers(self) -> None:
        """Sends the answers to the gateway."""
        if self._sending:
            return
        self._sending = True
        answers = []
        for draft in self._drafts:
            answers.append(
                {
                    'selected': list(draft['selected']),
                    'other': draft['other'].strip(),
                }
            )
        try:
            await self._gateway.answer_questions(self.request_id, answers)
        except gateway_client.GatewayError as error:
            self._sending = False
            self._error(error.message)
            return
        self.post_message(self.Done())

    @work(exclusive=True, group='answer')
    async def _dismiss(self) -> None:
        """Dismisses the request at the gateway."""
        try:
            await self._gateway.dismiss_request(self.request_id)
        except gateway_client.GatewayError as error:
            self._error(error.message)
            return
        self.post_message(self.Done())

    def _show(self) -> None:
        """Redraws the card for the current tab."""
        many = len(self._questions) > 1
        count = 'a question'
        if many:
            count = f'{len(self._questions)} questions'
        self.query_one('.request-heading', widgets.Static).update(
            Content.from_markup(
                '[b]$trader[/b] asks you $count',
                trader=self._request.get('trader', ''),
                count=count,
            )
        )
        reviewing = self._reviewing()
        question = self._question()
        tabs = self.query_one('.question-tabs', widgets.Static)
        tabs.display = many
        self._show_tabs()
        text = self.query_one('.question-text', widgets.Static)
        options = self.query_one('.question-options', widgets.OptionList)
        other = self.query_one('.question-other', widgets.Input)
        review = self.query_one('.question-review', widgets.Static)
        text.display = not reviewing
        options.display = not reviewing
        other.display = not reviewing
        review.display = reviewing
        if question is not None:
            heading = ''
            if not many:
                heading = f'[{question.get("header", "")}] '
            hint = ''
            if question.get('multi_select'):
                hint = '\nChoose all that apply.'
            text.update(
                Content.from_markup(
                    '[dim]$heading[/dim][b]$question[/b][dim]$hint[/dim]',
                    heading=heading,
                    question=question.get('question', ''),
                    hint=hint,
                )
            )
            other.value = self._drafts[self._tab]['other']
            self._show_options()
            options.highlighted = 0
            self._show_preview(0)
        else:
            self.query_one(
                '.question-preview', widgets.Markdown
            ).display = False
            review.update(self._review_content())
        self._show_hint()

    def _show_tabs(self) -> None:
        """Redraws the tab row: each question's header, ticked once answered, then Submit."""
        if len(self._questions) < 2:
            return
        parts = []
        for index, question in enumerate(self._questions):
            mark = '○'
            if self._is_answered(index):
                mark = '✓'
            tab = Content.from_markup(
                ' $mark $header ',
                mark=mark,
                header=question.get('header', ''),
            )
            if index == self._tab:
                tab = tab.stylize('reverse')
            parts.append(tab)
        submit = Content(' Submit ')
        if self._reviewing():
            submit = submit.stylize('reverse')
        parts.append(submit)
        self.query_one('.question-tabs', widgets.Static).update(
            Content('   ').join(parts)
        )

    def _show_options(self) -> None:
        """Redraws the options, with ticks for the picked ones."""
        question = self._question()
        if question is None:
            return
        options = self.query_one('.question-options', widgets.OptionList)
        highlighted = options.highlighted
        draft = self._drafts[self._tab]
        options.clear_options()
        for number, option in enumerate(question.get('options') or [], start=1):
            picked = option['label'] in draft['selected']
            mark = str(number)
            if question.get('multi_select'):
                mark = '☐'
                if picked:
                    mark = '☑'
            elif picked:
                mark = '✓'
            options.add_option(
                option_list.Option(
                    Content.from_markup(
                        '$mark  [b]$label[/b]  [dim]$description[/dim]',
                        mark=mark,
                        label=option['label'],
                        description=option.get('description', ''),
                    )
                )
            )
        if highlighted is not None:
            options.highlighted = highlighted

    def _show_preview(self, index: int | None) -> None:
        """Shows the preview of the highlighted option, when the question has previews.

        Args:
            index (int | None): The highlighted option.
        """
        question = self._question()
        preview = self.query_one('.question-preview', widgets.Markdown)
        if question is None:
            preview.display = False
            return
        options = question.get('options') or []
        has_previews = False
        for option in options:
            if option.get('preview'):
                has_previews = True
        preview.display = has_previews
        if not has_previews or index is None or index >= len(options):
            return
        preview.update(
            options[index].get('preview') or '*No preview for this choice.*'
        )

    def _show_hint(self) -> None:
        """Redraws the line of keys under the card."""
        parts = []
        if self._reviewing():
            parts.append('ctrl+s to submit')
            parts.append('shift+tab to go back')
        else:
            question = self._question() or {}
            count = len(question.get('options') or [])
            parts.append('↑↓ to move')
            parts.append(f'enter or 1-{count} to choose')
            parts.append(f'{count + 1} for Other')
            if len(self._questions) > 1:
                parts.append('tab for the next question')
            elif question.get('multi_select'):
                parts.append('ctrl+s to submit')
        parts.append('ctrl+x to dismiss')
        self.query_one('.request-hint', widgets.Static).update(
            Content.from_markup('[dim]$hint[/dim]', hint=' · '.join(parts))
        )

    def _review_content(self) -> Content:
        """The review tab: each question with its answer.

        Returns:
            Content: One line per question.
        """
        lines = [
            Content.from_markup('[b]Review your answers[/b]'),
        ]
        for index, question in enumerate(self._questions):
            answer = self._answer_text(self._drafts[index])
            if answer:
                lines.append(
                    Content.from_markup(
                        '[dim]$question[/dim]  $answer',
                        question=question.get('question', ''),
                        answer=answer,
                    )
                )
            else:
                lines.append(
                    Content.from_markup(
                        '[dim]$question[/dim]  [$error]Not answered yet[/]',
                        question=question.get('question', ''),
                    )
                )
        return Content('\n').join(lines)

    def _answer_text(self, draft: dict[str, Any]) -> str:
        """One question's answer in words.

        Args:
            draft (dict[str, Any]): The draft answer.

        Returns:
            str: The picked labels and the quoted Other answer, joined with commas.
        """
        parts = list(draft['selected'])
        if draft['other'].strip():
            parts.append(f'"{draft["other"].strip()}"')
        return ', '.join(parts)

    def _is_answered(self, index: int) -> bool:
        """Says whether a question has an answer.

        Args:
            index (int): The question.

        Returns:
            bool: True when an option is picked or Other has text.
        """
        draft = self._drafts[index]
        return bool(draft['selected']) or bool(draft['other'].strip())

    def _question(self) -> dict[str, Any] | None:
        """The question on the current tab.

        Returns:
            dict[str, Any] | None: The question, or None on the review tab.
        """
        if self._reviewing() or not self._questions:
            return None
        return self._questions[self._tab]

    def _reviewing(self) -> bool:
        """Says whether the review tab is showing.

        Returns:
            bool: True after the last question of several.
        """
        return len(self._questions) > 1 and self._tab == len(self._questions)

    def _error(self, text: str) -> None:
        """Shows a problem on the card.

        Args:
            text (str): The problem.
        """
        self.query_one('.request-error', widgets.Static).update(
            Content.from_markup('[$error]$text[/]', text=text)
        )
