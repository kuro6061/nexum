# Changelog

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
