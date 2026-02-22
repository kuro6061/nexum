# Timer Demo

Demonstrates the TIMER node type, which pauses workflow execution for a configurable delay without requiring a worker.

## Workflow

```
fetch (EFFECT) -> wait (TIMER, 5s) -> process (COMPUTE)
```

1. **fetch** - Simulates an API call
2. **wait** - Pauses for 5 seconds (server-side, no worker needed)
3. **process** - Processes the fetch result after the delay

## How TIMER works

- The server sets `scheduled_at` to `now + delay_seconds` when scheduling
- The poll query (`WHERE scheduled_at <= now()`) naturally suppresses the task
- When the timer expires, the server auto-completes the task on next poll
- No worker handler is needed - the server produces the output directly

## Run

```bash
# Start nexum server first
cargo run -p nexum-server

# In another terminal
pnpm start
```
