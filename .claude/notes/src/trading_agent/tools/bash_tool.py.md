# bash_tool.py and the four bash tools

The four tools share one terminal, so the session and the formatting of a command's outcome live in a shallow base class, and each tool is its own class in its own file, following the user's preference for one self-contained class per case. A non-zero exit status or a stopped command is returned as an error result, so the model notices a failure.

`bash_run` sets its own time limit 15 seconds above the terminal's, so that the terminal's restart message, not the registry's generic timeout, is what the model sees. Only `bash_run` closes the session, so the shared session is closed once when the trader stops.
