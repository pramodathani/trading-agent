# claude_code_backend_check.py

An `ANTHROPIC_API_KEY` in the environment is a failure, not a warning. Claude Code's authentication docs say that in non-interactive mode the key "is always used when present", which would silently bill the API instead of the user's Max subscription.
