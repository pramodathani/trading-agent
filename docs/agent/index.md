# The agent

This section explains how one desk thinks. Everything here applies to each of the four desks separately.

A desk does nothing until something wakes it: your message, a scheduled check, a heartbeat, a price alert, a fill, a webhook, or the daily rollover. Each of these becomes a **trigger** in the desk's queue, and the desk takes them one at a time. One trigger is one **turn**.

## A turn

In a turn the desk is given its instructions and the trigger, and its model either answers or asks for tools. The tools run, their results go back to the model, and the loop repeats until the model answers without asking for a tool, or until 20 rounds have passed.

<figure class="diagram">
--8<-- "docs/assets/diagrams/agent-loop.svg"
<figcaption>The agent loop for Qwen and Gemma. The orange dots are the model's tool calls going through the tool registry; the blue dots are results going back to the model. The loop guard stops a call that repeats with the same arguments.</figcaption>
</figure>

Claude works the same way, but the loop runs inside Claude Code, which trading-agent drives through the Claude Agent SDK. trading-agent's tools are served to it in the same process, Claude Code's own tools are switched off, and a hook refuses any tool that is not one of trading-agent's.

<figure class="diagram">
--8<-- "docs/assets/diagrams/claude-backend.svg"
<figcaption>The Claude backend. Claude Code runs the loop, calls trading-agent's tools through an in-process tool server, and every step is published on the event bus like a local model's.</figcaption>
</figure>

## The pages in this section

| Page | What it covers |
|---|---|
| [Models](models.md) | The backends, the model router and its fallback, and Claude through the Max subscription |
| [Tools](tools.md) | All 49 tools, the bash sandbox, the browser and web search |
| [Memory](memory.md) | Sessions, the daily rollover, notes, Memory.md, checkpoints and context compression |
| [Skills](skills.md) | Procedures the desks load when a task matches, and the ones they write themselves |
| [Subagents](subagents.md) | Helpers a desk hands tasks to, in parallel |
| [Scheduling and watching](scheduling.md) | Cron jobs, heartbeats, scheduled checks, the market watcher, price alerts and webhooks |
| [Extensions](extensions.md) | MCP servers, untrusted text, the knowledge base, hooks, packages and apps |
