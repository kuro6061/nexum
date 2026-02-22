# Nexum Core Examples

TypeScript demos showcasing Nexum's built-in node types and features.

## Prerequisites

- Nexum server running: `nexum dev` (or `cargo run --bin nexum-server`)
- Node.js 20+ and pnpm

## Running any demo

```bash
# Terminal 1: Start Nexum server
nexum dev

# Terminal 2: Run a demo
cd examples/core/<demo-name>
pnpm install
npx tsx run.ts
```

## Examples

| Demo | Description | Key nodes |
|------|-------------|-----------|
| `demo/` | Basic effect + compute chain — fetch and process data end-to-end | `.effect()`, `.compute()` |
| `llm-demo/` | LLM workflow with Gemini API — structured output + durability | `.llm()` |
| `parallel-demo/` | Fan-out execution — multiple branches run concurrently | `.effectAfter()` |
| `router-demo/` | Dynamic branching based on LLM output — routes to report or repair | `.router()` |
| `map-demo/` | MAP/REDUCE fan-out — process a list of items in parallel | `.map()`, `.reduce()` |
| `subworkflow-demo/` | Nested workflows — invoke a child workflow as a step | `.subworkflow()` |
| `approval-demo/` | Human-in-the-loop — pause execution and wait for manual approval | `.humanApproval()` |
| `versioning-demo/` | Safe workflow upgrades — SAFE/BREAKING/IDENTICAL detection | Versioning API |
| `timer-demo/` | Delayed execution — wait between steps with durable timers | `.effect()` + delay |

## Node type quick reference

```typescript
nexum.workflow('my-workflow')
  .effect('step',   OutputSchema, { handler: fn })          // side effects, exactly-once
  .compute('step2', OutputSchema, { handler: fn })          // pure functions, no retry
  .llm('step3',     OutputSchema, { prompt: '...' })        // LLM calls with structured output
  .router('step4',  { branches: { a: ..., b: ... } })       // dynamic branching
  .map('step5',     OutputSchema, { items: ctx => [...] })  // fan-out over list
  .humanApproval('step6', { approvers: ['admin'] })         // pause for human input
  .subworkflow('step7', childWorkflow)                      // nested workflow
  .build()
```

## Durability guarantees

Every node result is committed atomically to SQLite/PostgreSQL before the next node starts.
If a worker crashes mid-run, a fresh worker picks up exactly where the previous one left off.

```
step1 ✓ → step2 ✓ → [CRASH] → step3 ← fresh worker resumes here
```
