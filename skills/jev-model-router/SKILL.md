---
name: jev-model-router
description: Routes a task to an LLM under quality, cost, and latency constraints. Use when a task needs a model chosen from a catalog under quality, cost, or latency limits.
---

# JEV Model Router

Call the `model_route` MCP tool. Do not put API keys in the tool arguments.

Required arguments: `task`.

`JEV_PROVIDER` defaults to `local`. The tool ranks or filters candidates. It does not generate user-facing text and it does not execute the selected item.

Keys stay in the process environment.
