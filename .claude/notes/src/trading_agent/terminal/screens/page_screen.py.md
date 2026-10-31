# page_screen.py

The pages copy the web page's pages one for one: Traders, Activity, Trading, Sessions, Files, Checkpoints, Schedule, Skills, Extensions, Models, Channels, Settings and the package apps. Each is its own class in its own file; this base holds only the frame that every page shares (title line, Escape back to the chat, r to refresh, a timer, d for the next trader on pages that show one trader, and helpers for tables).

Every page opens with the focus on its first table or list. When a search box had the focus first, letter keys such as d (next trader) went into the box instead of reaching the page, and Textual's footer hid them.
