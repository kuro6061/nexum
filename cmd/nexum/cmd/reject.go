package cmd

import (
	"context"
	"fmt"
	"time"

	ngrpc "github.com/kuro6061/nexum/cmd/nexum/grpc"
	pb "github.com/kuro6061/nexum/cmd/nexum/proto"
	"github.com/spf13/cobra"
)

var rejectReason string

var rejectCmd = &cobra.Command{
	Use:   "reject <execution_id:node_id>",
	Short: "Reject a pending HUMAN_APPROVAL task",
	Long:  "Reject a pending HUMAN_APPROVAL task. The task ID format is execution_id:node_id.",
	Args:  cobra.ExactArgs(1),
	RunE:  runReject,
}

func init() {
	rejectCmd.Flags().StringVarP(&rejectReason, "reason", "r", "", "Rejection reason")
	rootCmd.AddCommand(rejectCmd)
}

func runReject(cmd *cobra.Command, args []string) error {
	executionID, nodeID, err := parseTaskID(args[0])
	if err != nil {
		return err
	}

	client, conn, err := ngrpc.Connect(serverAddr)
	if err != nil {
		return err
	}
	defer conn.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	resp, err := client.RejectTask(ctx, &pb.RejectRequest{
		ExecutionId: executionID,
		NodeId:      nodeID,
		Reason:      rejectReason,
	})
	if err != nil {
		return fmt.Errorf("RejectTask failed: %w", err)
	}

	if resp.Ok {
		fmt.Printf("Task %s rejected.\n", args[0])
	} else {
		fmt.Printf("Failed to reject task %s: %s\n", args[0], resp.Message)
	}

	return nil
}
