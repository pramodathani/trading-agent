# tokens.css

The colours, radii and sizes copy Claude Code web (claude.ai/code) as measured on 2026-10-18 with Chrome's computed styles, in both its dark and light modes.

| Token | Dark | Light | Where Claude Code uses it |
|---|---|---|---|
| `--color-bg-page` | `#151515` | `#fcfcfb` | The transcript area |
| `--color-bg-sidebar` | `#111111` | `#fafaf9` | The left sidebar |
| `--color-bg-raised` | `#20201f` | `#ffffff` | The prompt box |
| `--color-bg-selected` | 15% white | `#edece8` | The selected sidebar row |
| `--color-border` | 10% white | 10% of `#0b0b0b` | Card rings and the sidebar's right edge |
| `--color-text` / `-secondary` / `-muted` | `#f0efec` / `#c3c2b7` / `#898781` | `#0b0b0b` / `#52514e` / `#7b7974` | Body text, sidebar rows, labels |
| `--color-accent` | `#d97757` | `#c6613f` | Claude's clay brand colour |
| `--color-scrollbar` | `rgba(225, 224, 217, 0.35)` | `rgba(30, 30, 29, 0.35)` | Thin scrollbars |

Claude Code's own font, Anthropic Sans, is not available, so the stack is the fallback list Claude Code itself gives after it. The light-mode blue and the light accent's hover shade were not measured directly; they come from Claude Code's colour variables (`--accent-*`, `--brand-*`) because flipping its `data-mode` attribute only restyled part of the page.

The swatch colours for the context card are the ones Claude Code draws: blue for messages, orange for system tools, green for memory files, grey for the rest, and a dark grey for the autocompact buffer and for deferred items.

`--interface-zoom` is 1.1 because, on 2026-10-18, Chrome showed claude.ai at 110% zoom and the trading-agent page at 100%. Both use 14 px body text, Claude Code's "Medium" transcript size, so the whole page is scaled by the same 10% in CSS to look the same size side by side. CSS `zoom` on the root element keeps `height: 100%` filling the window in Chrome; this was checked in the browser before it was adopted. Set it to 1 if the browser's own zoom is raised for this site instead.
