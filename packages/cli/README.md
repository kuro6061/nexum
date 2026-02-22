# nexum-cli

> ⚠️ **Temporary implementation.** This Node.js CLI will be deprecated once the official Go CLI is released. The Go CLI will be distributed as a standalone binary (no Node.js required).

CLI for [Nexum](https://github.com/kuro6061/nexum) — Durable Execution Engine for LLM Agents.

## Install

```bash
npm install -g nexum-cli
```

## Commands

```
nexum dev        Start local Nexum server
nexum ps         List executions  [--workflow] [--status] [--limit]
nexum cancel     Cancel an execution  <execution-id>
nexum versions   List registered workflow versions  <workflow-id>
nexum approve    Approve a pending task  <execution-id> <node-id>
nexum reject     Reject a pending task   <execution-id> <node-id>
nexum approvals  List pending human approvals
nexum diff       Compare latest two workflow versions  <workflow-id>
```

## Migration

When the Go CLI is available, install it via:

```bash
# Coming soon — cross-platform binary, no Node.js required
```

This npm package will be marked deprecated at that point.

## License

MIT
