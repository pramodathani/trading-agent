# phone.css

The phone layout, modelled on the Claude Android app, for windows up to 760px wide: the Android app and phone browsers alike. It replaced the old 760px block in `layout.css`, which only wrapped the sidebar links across the top of the screen.

- The sidebar becomes a drawer that slides in from the left (`.app.drawer-open`), over a dimmed backdrop, opened by the ☰ button in the header.
- The header shows ☰, the trader menu in the centre, a short DRY or LIVE badge, the connection dot without words, and the side-panel button.
- The composer is a rounded card: the text box on its own row, then +, the model chip, and the round mic, stop and send buttons. `ChatPage` moves `ModelMenu` into the composer row on a phone and hides the footer unless voice input is listening.
- The side panel becomes a bottom sheet with a handle, over a backdrop; `sidePanelStore` never starts it open on a phone.
- `--interface-zoom` is 1 (the desktop's 1.1 zoom made phone text oversized), inputs use 16px text so Android does not zoom into them, and tap targets are at least 40 to 44px.
- `env(safe-area-inset-*)` padding keeps content clear of the status bar and gesture bar when the app draws edge to edge.

`:hover` rules elsewhere were left as they are; on a touchscreen a tapped item can keep its hover colour until the next tap, which was judged a small cost against touching every stylesheet.
