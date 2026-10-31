"""The pages and the terminal's actions in Textual's command palette (Ctrl+P).

Typical usage example:

  class TerminalApplication(App):
      COMMANDS = App.COMMANDS | {PageCommands}
"""

from functools import partial

from textual import command

from trading_agent.terminal.screens import page_catalogue


class PageCommands(command.Provider):
    """Offers every page, and switching trader, model and theme, in the command palette."""

    async def search(self, query: str) -> command.Hits:
        """Finds the pages and actions that match the typed text.

        Args:
            query (str): What was typed into the palette.

        Yields:
            command.Hit: One hit per matching page or action.
        """
        matcher = self.matcher(query)
        for page in page_catalogue.PageCatalogue().pages():
            text = f'{page.title} page'
            score = matcher.match(text)
            if score > 0:
                yield command.Hit(
                    score,
                    matcher.highlight(text),
                    partial(self.app.open_page, page.command),
                    help=page.description,
                )
        for text, action, description in self._actions():
            score = matcher.match(text)
            if score > 0:
                yield command.Hit(
                    score,
                    matcher.highlight(text),
                    action,
                    help=description,
                )

    async def discover(self) -> command.Hits:
        """Lists every page and action before anything is typed.

        Yields:
            command.DiscoveryHit: One hit per page or action.
        """
        for page in page_catalogue.PageCatalogue().pages():
            yield command.DiscoveryHit(
                f'{page.title} page',
                partial(self.app.open_page, page.command),
                help=page.description,
            )
        for text, action, description in self._actions():
            yield command.DiscoveryHit(text, action, help=description)

    def _actions(self) -> list[tuple[str, object, str]]:
        """The terminal's actions that are not pages.

        Returns:
            list[tuple[str, object, str]]: Each action's name, what to call, and what it does.
        """
        actions = [
            (
                'Switch theme',
                self.app.toggle_theme,
                'between the dark and light theme',
            ),
        ]
        chat = self.app.chat
        if chat is not None:
            actions.append(
                (
                    'Switch trader',
                    chat.action_pick_trader,
                    'show another trader in the chat',
                )
            )
            actions.append(
                (
                    'Choose model',
                    chat.action_pick_model,
                    'the model the trader tries first',
                )
            )
        return actions
