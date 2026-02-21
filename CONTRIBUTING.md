# Contributing to Nexum

Thank you for your interest in contributing!

## Development Setup

### Prerequisites
- Rust 1.75+ (`rustup update stable`)
- Node.js 20+ + pnpm (`npm install -g pnpm`)
- Python 3.11+ (for Python SDK)
- Protocol Buffers compiler (`protoc`)

### Build

```bash
# Rust server
cargo build

# TypeScript SDK + CLI
pnpm install
cd packages/sdk-typescript && pnpm build
cd packages/cli && pnpm build

# Python SDK
cd packages/sdk-python
pip install -e ".[dev]"
```

### Run Tests

```bash
# Rust unit tests
cargo test

# TypeScript integration (requires server running)
nexum dev &
cd examples/demo && npx tsx run.ts
```

## Project Structure

```
nexum/
├── crates/nexum-server/     # Rust gRPC server (core engine)
├── proto/nexum.proto        # gRPC service definition
├── packages/
│   ├── sdk-typescript/      # TypeScript SDK (@nexum/sdk)
│   ├── sdk-python/          # Python SDK (nexum-sdk)
│   └── cli/                 # nexum CLI
└── examples/                # Usage examples
```

## Submitting Changes

1. Fork the repo and create a branch: `git checkout -b feat/your-feature`
2. Make your changes and add tests
3. Run `cargo build` to verify Rust changes compile
4. Submit a PR with a clear description

## Areas for Contribution

- New node types (FORK, JOIN, TIMER)
- Additional language SDKs (Go, Java)
- Dashboard UI
- OpenTelemetry improvements
- Performance benchmarks
