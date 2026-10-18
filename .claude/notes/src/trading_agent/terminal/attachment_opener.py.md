# attachment_opener.py

The web page opens a desk's file in a new browser tab. A terminal cannot show a PDF or a spreadsheet, so the file is saved under `~/.local/state/trading-agent/downloads` and handed to `xdg-open`, which starts the desktop's default program. The process is started in its own session with its output discarded, so it neither blocks nor writes over the Textual screen. File names are reduced to safe characters because they come from the desk.
