<div align="center">
  <h1>⚡ Nexum</h1>
  <p><strong>Durable Execution Engine for LLM Agents</strong></p>
  <p>
    <a href="#quickstart">Quickstart</a> ·
    <a href="#why-nexum">Why Nexum</a> ·
    <a href="#architecture">Architecture</a> ·
    <a href="docs/">Docs</a>
  </p>
</div>

---

Nexum makes LLM agent workflows **crash-proof**. Define your agent as a typed DAG  ENexum handles retries, state persistence, exactly-once execution, and crash recovery automatically.

```typescript
const researchAgent = nexum.workflow<{ query: string }>('ResearchAgent')
  .effect('search', SearchResult, async (ctx, io) => {
    return await io.call(searchTool, ctx.input.query);  // auto-retried, exactly-once
  })
  .llm('analyze', Analysis, {
    model: 'gpt-4o',
    prompt: (ctx) => `Analyze: ${ctx.get('search').content}`,
  })
  .compute('score', Score, (ctx) => {
    return { score: ctx.get('analyze').confidence * 100 };
  })
  .build();
```

**Kill the process at any point. Nexum resumes from the last completed step.**

---

## Why Nexum?

| Problem | Without Nexum | With Nexum |
|---------|--------------|------------|
| LLM timeout on step 4/5 | Start over from step 1 | Resume from step 4 |
| Double-charging a customer | Manual dedup logic | Exactly-once by default |
| JSON parse failure | Crash | Auto-retry with repair |
| Deploy new workflow version | Risk breaking in-flight runs | Parallel active versions |

### vs. Temporal

Temporal is powerful but not LLM-native:

| | Temporal | Nexum |
|---|---|---|
| LLM non-determinism | Manual `getVersion()` everywhere | Handled by IR compiler |
| Large payloads (>4MB) | Custom Data Converter + Codec Server | Auto Claim Check |
| Setup | Temporal server + worker + codec | `nexum dev` (single binary) |
| TypeScript boilerplate | ~300 lines | ~100 lines |

See [`examples/analysis/temporal-compare/COMPARISON.md`](examples/analysis/temporal-compare/COMPARISON.md) for full benchmark.

---

## Quickstart

### Prerequisites
- Rust 1.75+
- Node.js 20+
- pnpm

### Install

```bash
# Clone
git clone https://github.com/your-org/nexum.git
cd nexum

# Build server
cargo build --release

# Install CLI
cd packages/cli && pnpm install && pnpm link --global
```

### Run your first workflow

```bash
# Terminal 1: Start Nexum server
nexum dev

# Terminal 2: Run demo
cd examples/core/demo && pnpm install && npx tsx run.ts
```

---

## Node Types

| Node | Description |
|------|-------------|
| `.effect()` | Side effects (API calls, DB writes)  Eexactly-once with auto-retry |
| `.compute()` | Pure functions  Edeterministic, no retry needed |
| `.llm()` | LLM calls with structured output enforcement |
| `.router()` | Dynamic branching based on LLM output |
| `.map()` | Fan-out: run handler for each item in parallel |
| `.reduce()` | Fan-in: aggregate MAP results |
| `.subworkflow()` | Invoke another workflow as a step |
| `.humanApproval()` | Pause and wait for human approval |

---

## Architecture

```
┌─────────────────────────────────────━E━E          Your Application          ━E━E ┌─────────────━E ┌──────────────━E ━E━E ━E @nexum/sdk ━E ━E nexum-sdk   ━E ━E━E ━E(TypeScript)━E ━E  (Python)   ━E ━E━E └──────┬──────━E └──────┬───────━E ━E└─────────┼────────────────┼──────────━E          ━E   gRPC         ━E┌─────────▼────────────────▼──────────━E━E          Nexum Server (Rust)        ━E━E ┌──────────━E ┌──────────────────━E ━E━E ━EScheduler━E ━E Event Sourcing  ━E ━E━E ━E Engine  ━E ━E  (SQLite/PG)    ━E ━E━E └──────────━E └──────────────────━E ━E└─────────────────────────────────────━E```

- **Server**: Rust + Tonic gRPC  Ehandles scheduling, durability, versioning
- **SDK**: TypeScript (Zod) or Python (Pydantic)  Eworkflow definition + worker
- **Storage**: SQLite (dev) or PostgreSQL (production)
- **IR**: Workflows compile to a deterministic DAG before execution

---

## Examples

| Example | Description |
|---------|-------------|
| `examples/core/demo/` | Basic effect + compute chain |
| `examples/core/llm-demo/` | LLM node with structured output |
| `examples/core/parallel-demo/` | Fan-out with `.effectAfter()` |
| `examples/core/router-demo/` | Dynamic branching with `.router()` |
| `examples/core/map-demo/` | MAP/REDUCE fan-out |
| `examples/core/approval-demo/` | Human-in-the-loop approval |
| `examples/core/subworkflow-demo/` | Nested workflow calls |
| `examples/core/versioning-demo/` | Safe workflow version upgrades |
| `examples/analysis/temporal-compare/` | Side-by-side Temporal comparison |

---

## Production Setup (PostgreSQL)

```bash
# docker-compose.yml included
docker compose up -d

export DATABASE_URL=postgres://nexum:nexum@localhost:5432/nexum
nexum dev
```

---

## Python SDK

```python
from nexum import workflow, NexumClient, worker
from pydantic import BaseModel

class Result(BaseModel):
    content: str
    score: float

my_workflow = (
    workflow("MyAgent")
    .effect("fetch", Result, handler=fetch_data)
    .compute("process", Output, handler=process_data)
    .build()
)
```

See [`packages/sdk-python/`](packages/sdk-python/) for full docs.

---

## CLI Reference

```bash
nexum dev                          # Start server (SQLite, port 50051)
nexum ps                           # List running executions
nexum cancel <execution-id>        # Cancel an execution
nexum versions <workflow-id>       # List registered versions
nexum diff <workflow-id>           # Compare latest two versions
nexum diff <workflow-id> --json    # JSON output (for CI/CD)
nexum approve <exec-id> <node-id>  # Approve a HUMAN_APPROVAL task
nexum reject <exec-id> <node-id>   # Reject a HUMAN_APPROVAL task
nexum approvals                    # List pending approvals
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT  Esee [LICENSE](LICENSE).
