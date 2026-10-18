# Models

Each desk lists its models in `backend_order`, most preferred first. Four kinds of backend are supported, and the table below shows what each reaches.

| Kind | Reaches | On this machine |
|---|---|---|
| `claude_code` | Claude, by running Claude Code through the Claude Agent SDK on the Max subscription | `claude`: Claude Opus 5.5 at medium effort, with a 1,000,000-token window; `claude_sonnet`: Claude Sonnet 5.5 at low effort, with a 200,000-token window |
| `deepseek` | DeepSeek's own API, paid per token | `deepseek`: DeepSeek V4 Pro, with a 1,000,000-token window and thinking on |
| `ollama` | A model served by Ollama | `qwen`: `qwen3.8:27b`, and `gemma`: `gemma4:31b`, each with a 32,768-token window |
| `openai_compatible` | OpenAI itself, or any server with the same API, such as llama.cpp, vLLM or LM Studio | none configured |

The general, intraday and positional desks use Claude Opus, then DeepSeek, then Qwen, then Gemma. The scalper wakes every two minutes, so it starts with Claude Sonnet at low effort instead, which leaves Opus's share of the Max subscription's limits to the other desks; after Sonnet its order is the same.

## Falling back

The model router tries a desk's models in order. When one is unavailable, because it failed, refused, or reached a usage limit, the router moves to the next and publishes a model switch. A desk moves away from Claude only when Claude cannot answer, and it comes back by itself.

<figure class="diagram">
--8<-- "docs/assets/diagrams/model-router.svg"
<figcaption>The model router tries Claude first; Claude has reached its limit, so the same turn goes to DeepSeek. The blue dots are Claude's refusal and DeepSeek's answer.</figcaption>
</figure>

A model that failed is not tried again until its waiting period ends. The table below lists how long each wait is.

| What happened | How long the model is skipped |
|---|---|
| An ordinary failure | 30 seconds after the first failure in a row, then 1 minute, then 5 minutes; a success resets it |
| Claude reached a subscription limit | Until the limit resets, as Claude reports it |
| DeepSeek answered "402 Insufficient Balance" | 15 minutes, because DeepSeek has no way to ask for the balance, so a top-up is noticed on the next try |

Each model keeps its own conversation, so when one takes over it is first told what was asked and answered on the turns it missed. If a model fails partway through a turn, the next one is also told which tool calls were already made for that turn and asked not to repeat them, so a handover cannot place the same order twice.

`/model deepseek`, or the model menu under the message box, makes a desk try that model first from now on, and `/model auto` restores the configured order. Choosing another Claude model, such as Haiku, changes the model inside the running Claude session, so the conversation carries on. Both last until the gateway restarts.

## How hard a model thinks

`effort` in `trading_agent.toml` sets how hard Claude thinks, and `thinking` turns reasoning on or off for the other models. `/think` changes it for every model of a desk from the next turn, until the gateway restarts, as [Talking to a desk](../using/chat.md#slash-commands) describes.

## Claude through the Max subscription

trading-agent uses Claude through your Max subscription, never the API. The table below lists what could interrupt a Claude turn, and how each is avoided.

| Could interrupt | How it is avoided |
|---|---|
| A permission prompt | `permission_mode="bypassPermissions"` with no settings files loaded, so no rule of Claude Code's can ask; trading-agent's own [permission prompts](../using/questions-and-permissions.md#permission-prompts) are a separate thing and never block a turn |
| A login prompt | The one-year token from `claude setup-token`, passed as `CLAUDE_CODE_OAUTH_TOKEN` |
| A usage limit | Claude's rate-limit event marks it unavailable until the limit resets, and the router falls back |
| Billing the API by mistake | `ANTHROPIC_API_KEY` is removed from every Claude Code process; the doctor fails if it is set |

The Models page shows Claude's five-hour and weekly limits as Claude reports them, and each desk's usage today. Claude's cost there is what the same tokens would cost on the API, as a guide to how quickly the limits are used; nothing is billed per token.

## DeepSeek

DeepSeek speaks the same protocol as OpenAI, with three differences that the `deepseek` backend handles. The table below lists them.

| Difference | What the backend does |
|---|---|
| With tools offered, DeepSeek requires its earlier thinking to be sent back with every earlier answer | The conversation keeps the thinking and sends it back |
| Prompt tokens cost less when DeepSeek's cache holds them, and off-peak hours cost half | Each call is costed from the cache hits, the cache misses and the time of day, and `/usage` and the Models page show the result |
| V4 Pro cannot read pictures | `vision = false` leaves pictures out, and the model is told so |

The key is `DEEPSEEK_API_KEY` in `.env`. Until it is there, DeepSeek is skipped, and `bin/trading-agent doctor` checks the key without showing it.
