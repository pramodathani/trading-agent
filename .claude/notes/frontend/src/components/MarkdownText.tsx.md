# MarkdownText.tsx

Renders the trader's answers, streamed text and messages as Markdown, as Claude Code does; the user's own messages stay plain text. `react-markdown` with `remark-gfm` gives tables, task lists and strikethrough. It never renders raw HTML from the text, so a reply that contains HTML, or a prompt-injected one, cannot add elements or scripts to the page.

Code blocks are coloured by highlight.js's core with twelve registered languages (bash, diff, ini/toml, JavaScript, JSON, Markdown, Python, shell, SQL, TypeScript, XML/HTML, YAML). `rehype-highlight` was tried first, but it bundles highlight.js's 37 "common" languages whatever is registered and doubled the page script, so the code block calls highlight.js directly. highlight.js escapes the code text itself, which is what makes `dangerouslySetInnerHTML` safe there.

The sizes and spacing come from Claude Code's transcript, measured on 2026-10-18: paragraphs and lists 10.5 px apart, list items 3.5 px apart with 28 px indentation, tables framed by a 1 px ring with 6 px corners and a lightly filled header row, and inline code at 0.9 em in a reddish colour on a faint fill with a 1 px ring and 5 px corners.
