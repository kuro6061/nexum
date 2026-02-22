package grpc

import (
	"fmt"

	pb "github.com/kuro6061/nexum/cmd/nexum/proto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

const DefaultServer = "localhost:50051"

// Connect creates a gRPC client connection and returns a NexumServiceClient.
func Connect(server string) (pb.NexumServiceClient, *grpc.ClientConn, error) {
	conn, err := grpc.Dial(server, grpc.WithTransportCredentials(insecure.NewCredentials())) //nolint:staticcheck
	if err != nil {
		return nil, nil, fmt.Errorf("failed to connect to %s: %w", server, err)
	}
	client := pb.NewNexumServiceClient(conn)
	return client, conn, nil
}
