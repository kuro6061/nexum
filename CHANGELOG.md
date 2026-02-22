# Changelog

## [0.2.0] - 2026-02-22

### Added
- Unit tests: Rust server (4), TypeScript SDK (14), Python SDK (15) = 33 tests total
- JSDoc on all `WorkflowBuilder` public methods (TypeScript SDK)
- Sphinx docstrings on `WorkflowBuilder` and `workflow()` (Python SDK)
- `typedoc` setup for TypeScript SDK API docs (`pnpm docs`)
- `examples/core/README.md` — index and quick-start for all TS demos
- `examples/integrations/README.md` — integration pattern guide
- Quantitative Temporal benchmark with live measured numbers (BENCHMARK.md)
  - Boilerplate: Nexum 50% vs Temporal 67%
  - 1MB payload DB storage: 192 bytes (pointer) vs 1,048,576 bytes (Temporal)
  - Crash recovery: 0 steps re-executed, 0.57s scheduling overhead

### Changed
- Examples reorganized: `examples/core/`, `examples/integrations/`, `examples/analysis/`
- `autogen-recovery-demo/` merged into `autogen-nexum/`
- All Python integrations now have `requirements.txt` with `-e ../../../packages/sdk-python`
- Removed `sys.path.insert` hacks from all 25 Python integration files
- `TASK_TIMEOUT_SECS` constant now used in stale task reclaim queries (was hardcoded)

### Fixed
- 4 `.unwrap()` panics replaced with proper error handling
  - Claim check pointer serialization → `map_err(Status::internal)`
  - Event payload serialization → `unwrap_or_else(|| "{}")`
  - Metrics server bind failure → log warning + graceful return (no crash)
  - Metrics server serve error → log error (no crash)
- Rust compiler warnings eliminated (9 → 0)

## [0.1.0] - 2026-02-21

### Added
- Core durable execution engine (Rust + gRPC)
- TypeScript SDK with Zod schema validation
- Python SDK with Pydantic schema validation
- Node types: EFFECT, COMPUTE, LLM, ROUTER, MAP, REDUCE, SUBWORKFLOW, HUMAN_APPROVAL
- Formal workflow versioning (SAFE/BREAKING/IDENTICAL detection)
- Parallel active versions for zero-downtime deploys
- Exactly-once execution with Claim Check for large payloads
- Worker concurrency with configurable semaphore
- nexum CLI: dev, ps, cancel, versions, diff, approve, reject, approvals
- Prometheus metrics + OpenTelemetry tracing
- SQLite (dev) and PostgreSQL (production) support
- Docker Compose setup for production
- 9 example workflows including Temporal comparison
