"""A dialog for choosing which model a trader tries first, as the web page's model menu does.

It lists the trader's backends in their configured order, then each provider's other models, then "Auto" for the configured order with fallback. The web page shows the other models in submenus; here they follow under their provider's heading. Keys 1 to 9 pick a backend directly.

It returns a (backend, model) pair, with (None, None) for Auto, or None when the user presses Escape.

Typical usage example:

  app.push_screen(ModelPicker(trader_summary), on_chosen)
"""

from typing import Any, ClassVar

from textual import binding
from textual import containers
from textual import events
from textual import screen
from textual import widgets
from textual.content import Content
from textual.widgets import option_list

from trading_agent.terminal import model_names

ModelChoice = tuple[str | None, str | None]


class ModelPicker(screen.ModalScreen[ModelChoice | None]):
    """The model list."""

    BINDINGS: ClassVar[list[binding.BindingType]] = [
        binding.Binding('escape', 'cancel', 'Close'),
    ]

    def __init__(self, trader: dict[str, Any]):
        """Creates the dialog.

        Args:
            trader (dict[str, Any]): The trader's summary from GET /api/traders, with its backends.
        """
        super().__init__(classes='picker-screen')
        self._trader = trader
        self._names = model_names.ModelNames()
        self._choices: list[ModelChoice | None] = []
        self._rows: list[option_list.Option] = []
        self._current_row: int | None = None
        self._build()

    def compose(self):
        """Builds the dialog.

        Yields:
            Widget: The title, the list and the hint.
        """
        with containers.Vertical(classes='picker'):
            yield widgets.Static(
                Content.from_markup(
                    '[b]Model for $trader[/b]', trader=self._trader['name']
                ),
                classes='picker-title',
            )
            yield widgets.OptionList(*self._rows, id='model-options')
            yield widgets.Static(
                '[dim]↑↓ to move · enter or 1-9 to choose · esc to close[/dim]',
                classes='picker-hint',
            )

    def on_mount(self) -> None:
        """Highlights the current choice."""
        options = self.query_one('#model-options', widgets.OptionList)
        options.highlighted = self._current_index()
        options.focus()

    def on_key(self, event: events.Key) -> None:
        """Picks a backend with its number key.

        Args:
            event (events.Key): The key press.
        """
        if not event.character or not event.character.isdigit():
            return
        number = int(event.character)
        backends = self._trader.get('backends') or []
        if 1 <= number <= len(backends):
            event.stop()
            self.dismiss(
                (
                    backends[number - 1]['name'],
                    None,
                )
            )

    def on_option_list_option_selected(
        self, event: widgets.OptionList.OptionSelected
    ) -> None:
        """Returns the chosen backend and model.

        Args:
            event (widgets.OptionList.OptionSelected): The choice.
        """
        choice = self._choices[event.option_index]
        if choice is None:
            return
        self.dismiss(choice)

    def action_cancel(self) -> None:
        """Closes the dialog without a choice."""
        self.dismiss(None)

    def _build(self) -> None:
        """Builds the rows: the backends, each provider's other models, then Auto."""
        backends = self._trader.get('backends') or []
        for number, backend in enumerate(backends, start=1):
            self._add(
                Content.from_markup(
                    '$number  [b]$label[/b]  [dim]$name[/dim]$tick',
                    tick=self._tick(backend['name'], None),
                    number=str(number),
                    label=self._names.label(backend.get('model')),
                    name=backend['name'],
                ),
                (
                    backend['name'],
                    None,
                ),
            )
        for kind, models in self._providers(backends):
            self._add(
                Content.from_markup(
                    '[dim]$provider, other models[/dim]',
                    provider=self._names.provider(kind),
                ),
                None,
                disabled=True,
            )
            for model, backend_name in models:
                self._add(
                    Content.from_markup(
                        '·  $label  [dim]via $name[/dim]$tick',
                        tick=self._tick(backend_name, model),
                        label=self._names.label(model),
                        name=backend_name,
                    ),
                    (
                        backend_name,
                        model,
                    ),
                )
        auto_tick = ''
        if not self._trader.get('preferred_model'):
            auto_tick = '  ✓'
        self._add(
            Content.from_markup(
                '[b]Auto[/b]  [dim]configured order, with fallback[/dim]$tick',
                tick=auto_tick,
            ),
            (
                None,
                None,
            ),
        )

    def _add(
        self,
        prompt: Content,
        choice: ModelChoice | None,
        disabled: bool = False,
    ) -> None:
        """Adds one row.

        Args:
            prompt (Content): The row's text.
            choice (ModelChoice | None): What choosing it returns, or None for a heading.
            disabled (bool): Whether the row cannot be chosen.
        """
        if str(prompt).endswith('✓'):
            self._current_row = len(self._rows)
        self._rows.append(option_list.Option(prompt, disabled=disabled))
        self._choices.append(choice)

    def _providers(
        self, backends: list[dict[str, Any]]
    ) -> list[tuple[str, list[tuple[str, str]]]]:
        """Groups the backends' other models by provider, each run by the first backend that offers it.

        Args:
            backends (list[dict[str, Any]]): The trader's backends, in order.

        Returns:
            list[tuple[str, list[tuple[str, str]]]]: Each provider kind with its (model, backend name) pairs, in the order they first appear.
        """
        providers: list[tuple[str, list[tuple[str, str]]]] = []
        for backend in backends:
            others = backend.get('other_models') or []
            if not others:
                continue
            models = None
            for kind, existing in providers:
                if kind == backend.get('kind'):
                    models = existing
            if models is None:
                models = []
                providers.append(
                    (
                        backend.get('kind', ''),
                        models,
                    )
                )
            for model in others:
                already = False
                for known_model, _ in models:
                    if known_model == model:
                        already = True
                if not already:
                    models.append(
                        (
                            model,
                            backend['name'],
                        )
                    )
        return providers

    def _tick(self, backend_name: str, model: str | None) -> str:
        """A tick for the current choice.

        Args:
            backend_name (str): The row's backend.
            model (str | None): The row's other model, or None for the backend's configured model.

        Returns:
            str: Two spaces and "✓" for the current choice, otherwise an empty string.
        """
        if self._trader.get('preferred_model') != backend_name:
            return ''
        active = None
        configured = None
        for backend in self._trader.get('backends') or []:
            if backend['name'] == backend_name:
                active = backend.get('active_model')
                configured = backend.get('model')
        if model is None:
            if active is None or active == configured:
                return '  ✓'
            return ''
        if active == model:
            return '  ✓'
        return ''

    def _current_index(self) -> int:
        """The row of the current choice.

        Returns:
            int: Its index, or the Auto row's.
        """
        if self._current_row is not None:
            return self._current_row
        return len(self._rows) - 1
