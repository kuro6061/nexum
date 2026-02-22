# nexum-sdk

Python SDK for [Nexum](https://github.com/kuro6061/nexum) — Durable Execution Engine for LLM Agents.

## Install

```bash
pip install nexum-py
```

## Quick Start

```python
from nexum import workflow, worker

wf = (
    workflow("ResearchAgent")
    .effect("search", search_tool)
    .compute("summarize", lambda ctx: ctx.get("search")["content"][:500])
    .build()
)

w = worker(server_address="localhost:50051")
w.register(wf)
w.start()
```

Requires a running [Nexum server](https://github.com/kuro6061/nexum). Start locally with:

```bash
npx @nexum/cli dev
```

## License

MIT
