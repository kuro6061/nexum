# Go CLI for Nexum - Implementation Summary

## What was built

A Go CLI (`nexum`) using Cobra that communicates with the nexum-server via gRPC.

## Commands

| Command | Description |
|---------|-------------|
| `nexum dev` | Start local nexum-server with SQLite (finds binary in `./target/{debug,release}/` or `$PATH`) |
| `nexum ps` | List running executions via `ListExecutions` RPC |
| `nexum cancel <execution_id>` | Cancel an execution via `CancelExecution` RPC |
| `nexum versions <workflow_id>` | List workflow versions via `ListWorkflowVersions` RPC |
| `nexum approvals` | List pending HUMAN_APPROVAL tasks via `GetPendingApprovals` RPC |
| `nexum approve <exec_id:node_id>` | Approve a task via `ApproveTask` RPC (`-c` for comment) |
| `nexum reject <exec_id:node_id>` | Reject a task via `RejectTask` RPC (`-r` for reason) |

## Global flags

- `--server` / `-s` - gRPC server address (default: `localhost:50051`)

## File structure

```
cmd/nexum/
  main.go              - Entry point
  go.mod               - Go module definition
  cmd/
    root.go            - Root cobra command, --server flag
    dev.go             - nexum dev (start local server)
    ps.go              - nexum ps (list executions)
    cancel.go          - nexum cancel
    versions.go        - nexum versions
    approvals.go       - nexum approvals
    approve.go         - nexum approve
    reject.go          - nexum reject
  grpc/
    client.go          - gRPC connection helper (insecure, for local dev)
  proto/
    nexum.proto        - Copy of the proto definition
    nexum.pb.go        - Hand-written protobuf message types (using protowire)
    nexum_grpc.pb.go   - Hand-written gRPC client stubs (custom binary codec)
```

## Proto approach

Since `protoc` / `protoc-gen-go` may not be available, the protobuf types are hand-written using `google.golang.org/protobuf/encoding/protowire` for binary serialization. A custom gRPC codec is registered that delegates to `encoding.BinaryMarshaler` / `BinaryUnmarshaler` interfaces, making the hand-written types work seamlessly with `grpc.Invoke`.

## CI/CD

Added `release-go-cli` job to `.github/workflows/publish.yml`:
- Triggers on `v*` tags (same as npm/PyPI publishing)
- Builds for linux/amd64, darwin/amd64, darwin/arm64, windows/amd64
- Cross-compiles with `CGO_ENABLED=0` for static binaries
- Uploads binaries to the GitHub Release via `gh release upload`

## Dependencies

- `github.com/spf13/cobra` v1.8.0 - CLI framework
- `google.golang.org/grpc` v1.62.0 - gRPC client
- `google.golang.org/protobuf` v1.33.0 - Protobuf wire encoding (protowire)
