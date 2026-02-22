package cmd

import (
	"context"
	"fmt"
	"time"

	ngrpc "github.com/kuro6061/nexum/cmd/nexum/grpc"
	pb "github.com/kuro6061/nexum/cmd/nexum/proto"
	"github.com/spf13/cobra"
)

var cancelCmd = &cobra.Command{
	Use:   "cancel <execution_id>",
	Short: "Cancel a running execution",
	Args:  cobra.ExactArgs(1),
	RunE:  runCancel,
}

func init() {
	rootCmd.AddCommand(cancelCmd)
}

func runCancel(cmd *cobra.Command, args []string) error {
	executionID := args[0]

	client, conn, err := ngrpc.Connect(serverAddr)
	if err != nil {
		return err
	}
	defer conn.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	resp, err := client.CancelExecution(ctx, &pb.CancelRequest{
		ExecutionId: executionID,
	})
	if err != nil {
		return fmt.Errorf("CancelExecution failed: %w", err)
	}

	if resp.Ok {
		fmt.Printf("Execution %s cancelled.\n", executionID)
	} else {
		fmt.Printf("Failed to cancel execution %s: %s\n", executionID, resp.Message)
	}

	return nil
}
