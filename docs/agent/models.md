# Models

Each desk lists its models in `backend_order`, most preferred first. Three kinds of backend are supported.

| Kind | Reaches | On this machine |
|---|---|---|
| `claude_code` | Claude, by running Claude Code through the Claude Agent SDK | `claude`: Claude Opus, with a 1,000,000-token window |
| `ollama` | A model served by Ollama | `qwen`: `qwen3.8:27b`, and `gemma`: `gemma4:31b`, each with a 32,768-token window |
| `openai_compatible` | OpenAI itself, or any server with the same API, such as llama.cpp, vLLM or LM Studio | none configured |

## Falling back

The model router tries a desk's models in order. When one is unavailable, because it failed, refused, or reached a usage limit, the router moves to the next and publishes a model switch. A model that failed is not tried again until its waiting period ends: 30 seconds after the first failure in a row, then 1 minute, then 5 minutes. A success resets it.

<figure class="diagram">
--8<-- "docs/assets/diagrams/model-router.svg"
<figcaption>The model router tries Claude first; when Claude is unavailable, the turn goes to Qwen, then Gemma. The blue dot is the answer from whichever model took the turn.</figcaption>
</figure>

Each model keeps its own conversation, so when one takes over it is first told what was asked and answered on the turns it missed. `/model qwen` makes a desk try Qwen first from now on, and `/model auto` restores the configured order.

## Claude through the Max subscription

trading-agent uses Claude through your Max subscription, never the API. The table below lists what could interrupt a Claude turn, and how each is avoided.

| Could interrupt | How it is avoided |
|---|---|
| A permission prompt | `permission_mode="bypassPermissions"` with no settings files loaded, so no rule can ask |
| A login prompt | The one-year token from `claude setup-token`, passed as `CLAUDE_CODE_OAUTH_TOKEN` |
| A usage limit | Claude's rate-limit event marks it unavailable, and the router falls back |
| Billing the API by mistake | `ANTHROPIC_API_KEY` is removed from every Claude Code process; the doctor fails if it is set |

The Models page shows Claude's five-hour and weekly limits as Claude reports them, and each desk's usage today. Claude's cost there is what the same tokens would cost on the API, as a guide to how quickly the limits are used; nothing is billed per token.
