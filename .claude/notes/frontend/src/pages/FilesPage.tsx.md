# FilesPage.tsx

The user's files can only be changed by the user, so this page is where that happens without opening an editor on the machine. Saving TradingRules.md is checked by the risk engine's own reader first; in the browser check on 2026-10-17, text with no limits block was refused with the reader's reason and the file's checksum was unchanged.

Switching files with unsaved changes asks inline instead of with a browser pop-up, because pop-ups block the page and automated checks.

Proposals are listed with their diff, pending first. Accepting writes the proposed text to the file; rejecting keeps the file. Decided proposals are hidden unless asked for.
