# sidePanel/

The column of cards on the chat page copies the right-hand panel of Claude Code web: 280 px wide, 12 px from the window's right edge, each card a 1 px ring with 10 px corners, a 12 px title with a fold chevron, and 12 px rows.

The chat transcript scrolls in one box that runs the full width of the content area, under the panel, which is why its scrollbar sits at the window's right edge as in Claude Code. The transcript column and the composer are pushed left by `--panel-space` so that nothing hides behind the panel. Below 1100 px the panel overlays the chat instead of taking space.

The panel opens by default on screens at least 1100 px wide; after that the header button's choice, and each card's folded state, are remembered in localStorage by `sidePanelStore`.

Each card is its own component in its own file. The panel polls the context route every 20 s and the account every 15 s, and asks again at once when the trader's events show a finished turn, a compaction, an order or a fill. Orders placed, cancelled and trades are counted from today's journal events for the trader (`order` events with action `placed` or `cancelled`, `fill` events with a filled quantity); open orders come from the trader order book and stocks held from the risk ledger's owners.
