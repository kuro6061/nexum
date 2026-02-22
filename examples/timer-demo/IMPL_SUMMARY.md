# TIMER Node Implementation Summary

## Overview

The TIMER node pauses workflow execution for a configurable delay, then auto-continues without requiring a worker handler. It leverages the existing `scheduled_at` infrastructure in the task queue.

## Changes by Layer

### 1. Rust Server (`crates/nexum-server/src/main.rs`)

**Dependency added:** `chrono` (for UTC timestamp in output)

**`schedule_ready_nodes`** - When a TIMER node becomes ready:
- Reads `delay_seconds` from the IR node definition
- Sets `scheduled_at = now() + delay_seconds` (SQLite: `datetime('now', '+N seconds')`, PostgreSQL: `NOW() + INTERVAL 'N seconds'`)
- The existing poll query (`WHERE scheduled_at <= now()`) naturally suppresses the task until the delay elapses

**`poll_task`** - When a worker polls and picks up a TIMER task:
- Auto-completes it server-side immediately (no work dispatched to worker)
- Produces output: `{ waited_until: <ISO 8601>, delay_seconds: N }`
- Inserts `NodeCompleted` event
- Schedules downstream nodes and checks execution completion
- Returns `has_task: false` so the worker continues polling

### 2. TypeScript SDK (`packages/sdk-typescript/src/builder.ts`)

- Added `'TIMER'` to the `NodeDef.type` union
- Added `delaySeconds?: number` field to `NodeDef`
- Added `.timer(id, options)` method accepting `{ delaySeconds: number }` or `{ scheduledAt: Date }`
- Output type: `{ waited_until: string; delay_seconds: number }`
- IR includes `delay_seconds` field for the server to read
- TIMER handler throws (should never be called; server handles it)

### 3. TypeScript Worker (`packages/sdk-typescript/src/worker.ts`)

- Added TIMER case before HUMAN_APPROVAL in `processTask`
- Safety fallback: if somehow a TIMER task reaches the worker, it completes it with the expected output format
- In practice, the server auto-completes TIMER tasks during poll, so this code path is defensive only

### 4. Python SDK (`packages/sdk-python/nexum/builder.py` + `worker.py`)

- Added `delay_seconds` parameter to `NodeDef`
- Added `.timer(node_id, delay_seconds)` method to `WorkflowBuilder`
- IR output includes `delay_seconds` when present
- Worker: added TIMER early-return in `_execute_task` (defensive, same as TS)

### 5. Example (`examples/timer-demo/`)

- `run.ts`: 3-step workflow: `fetch (EFFECT)` -> `wait (TIMER, 5s)` -> `process (COMPUTE)`
- Demonstrates timer pausing execution for 5 seconds between fetch and process
- Polls and prints status until completion

## Key Design Decisions

1. **Server-side auto-complete**: TIMER tasks are completed by the server during `poll_task`, not by the worker. This means no worker needs to be running for the timer to fire (as long as any worker polls eventually).

2. **Leverages existing infrastructure**: No schema changes needed. The `scheduled_at` column and the existing poll query (`WHERE scheduled_at <= datetime('now')`) already handle future-dated tasks.

3. **Dual-DB support**: Both SQLite (`datetime('now', '+N seconds')`) and PostgreSQL (`NOW() + INTERVAL 'N seconds'`) are handled, following the same pattern as retry backoff.

4. **Defensive worker handlers**: Both TS and Python workers include TIMER handlers as safety fallbacks, though the server should always auto-complete these tasks.
