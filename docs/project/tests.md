# Tests

The suite has 578 tests in 57 files and runs in about 80 seconds, most of it the terminal program's screen tests:

```bash
.venv/bin/pytest
.venv/bin/pytest tests/test_risk_engine.py
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

The tests use stand-ins for models, UBI, Telegram and systemd, so they need no GPU, no network and no running service. The table below lists what the main files cover.

| Area | Files |
|---|---|
| Risk and orders | `test_risk_engine.py`, `test_kill_switch.py`, `test_order_tools.py`, `test_trading_tools.py`, `test_traders.py` |
| The agent | `test_agent_loop.py`, `test_context_compression.py`, `test_context_usage.py`, `test_steering.py`, `test_trader_runtime.py`, `test_slash_commands.py`, `test_side_questions.py` |
| Models | `test_model_router.py`, `test_fallback_order.py`, `test_model_choice_route.py`, `test_claude_code_backend.py`, `test_deepseek_backend.py`, `test_ollama_backend.py`, `test_openai_compatible_backend.py` |
| Questions and permissions | `test_user_requests.py`, `test_permissions.py`, `test_telegram_requests.py`, `test_telegram_approvals.py` |
| Pictures and documents | `test_attachments.py`, `test_pictures.py` |
| Memory and skills | `test_memory.py`, `test_skills.py`, `test_subagents.py` |
| Tools | `test_bash_sandbox.py`, `test_browser_session.py`, `test_web_tools.py`, `test_file_tools.py`, `test_tool_registry.py` |
| Scheduling | `test_scheduling.py`, `test_market_watch.py` |
| Extensions | `test_extensions.py`, `test_mcp.py`, `test_apps.py` |
| The gateway | `test_gateway.py`, `test_gateway_api.py`, `test_frontend_routes.py`, `test_token_redacting_filter.py` |
| Telegram and going live | `test_telegram.py`, `test_preflight.py` |
| The terminal program | `test_chat_transcript.py`, `test_terminal_describers.py`, `test_gateway_client.py`, `test_message_client.py`, `test_command_catalogue.py`, `test_terminal_chat_screen.py`, `test_terminal_pages.py`, `test_terminal_attribute_names.py` |

Some things can only be checked live, and were: each backend against its real model, the browser against real pages, the sandbox against bwrap, UBI's account and quotes, the service's restart after `kill -9`, the web page in Chrome, and the terminal program against a copy of the gateway, driven key by key with Textual's test pilot. The checks that need a trading day are in [Going live](../going_live.md).
