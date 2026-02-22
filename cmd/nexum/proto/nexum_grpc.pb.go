// Hand-written gRPC client stubs for NexumService.
// Uses a custom codec that delegates to MarshalBinary/UnmarshalBinary.

package proto

import (
	"context"
	"encoding"

	"google.golang.org/grpc"
	grpcEncoding "google.golang.org/grpc/encoding"
)

// binaryCodec uses encoding.BinaryMarshaler/BinaryUnmarshaler.
type binaryCodec struct{}

func (binaryCodec) Marshal(v interface{}) ([]byte, error) {
	return v.(encoding.BinaryMarshaler).MarshalBinary()
}

func (binaryCodec) Unmarshal(data []byte, v interface{}) error {
	return v.(encoding.BinaryUnmarshaler).UnmarshalBinary(data)
}

func (binaryCodec) Name() string { return "proto" }

func init() {
	grpcEncoding.RegisterCodec(binaryCodec{})
}

const serviceName = "/nexum.NexumService/"

// NexumServiceClient is the client interface for NexumService.
type NexumServiceClient interface {
	ListExecutions(ctx context.Context, in *ListRequest, opts ...grpc.CallOption) (*ListResponse, error)
	CancelExecution(ctx context.Context, in *CancelRequest, opts ...grpc.CallOption) (*AckResponse, error)
	ListWorkflowVersions(ctx context.Context, in *ListVersionsRequest, opts ...grpc.CallOption) (*ListVersionsResponse, error)
	ApproveTask(ctx context.Context, in *ApproveRequest, opts ...grpc.CallOption) (*AckResponse, error)
	RejectTask(ctx context.Context, in *RejectRequest, opts ...grpc.CallOption) (*AckResponse, error)
	GetPendingApprovals(ctx context.Context, in *EmptyRequest, opts ...grpc.CallOption) (*PendingApprovalsResponse, error)
}

type nexumServiceClient struct {
	cc grpc.ClientConnInterface
}

// NewNexumServiceClient creates a new NexumService gRPC client.
func NewNexumServiceClient(cc grpc.ClientConnInterface) NexumServiceClient {
	return &nexumServiceClient{cc}
}

func (c *nexumServiceClient) ListExecutions(ctx context.Context, in *ListRequest, opts ...grpc.CallOption) (*ListResponse, error) {
	out := new(ListResponse)
	err := c.cc.Invoke(ctx, serviceName+"ListExecutions", in, out, opts...)
	return out, err
}

func (c *nexumServiceClient) CancelExecution(ctx context.Context, in *CancelRequest, opts ...grpc.CallOption) (*AckResponse, error) {
	out := new(AckResponse)
	err := c.cc.Invoke(ctx, serviceName+"CancelExecution", in, out, opts...)
	return out, err
}

func (c *nexumServiceClient) ListWorkflowVersions(ctx context.Context, in *ListVersionsRequest, opts ...grpc.CallOption) (*ListVersionsResponse, error) {
	out := new(ListVersionsResponse)
	err := c.cc.Invoke(ctx, serviceName+"ListWorkflowVersions", in, out, opts...)
	return out, err
}

func (c *nexumServiceClient) ApproveTask(ctx context.Context, in *ApproveRequest, opts ...grpc.CallOption) (*AckResponse, error) {
	out := new(AckResponse)
	err := c.cc.Invoke(ctx, serviceName+"ApproveTask", in, out, opts...)
	return out, err
}

func (c *nexumServiceClient) RejectTask(ctx context.Context, in *RejectRequest, opts ...grpc.CallOption) (*AckResponse, error) {
	out := new(AckResponse)
	err := c.cc.Invoke(ctx, serviceName+"RejectTask", in, out, opts...)
	return out, err
}

func (c *nexumServiceClient) GetPendingApprovals(ctx context.Context, in *EmptyRequest, opts ...grpc.CallOption) (*PendingApprovalsResponse, error) {
	out := new(PendingApprovalsResponse)
	err := c.cc.Invoke(ctx, serviceName+"GetPendingApprovals", in, out, opts...)
	return out, err
}
