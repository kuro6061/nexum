package cmd

import (
	"context"
	"fmt"
	"strings"
	"time"

	ngrpc "github.com/kuro6061/nexum/cmd/nexum/grpc"
	pb "github.com/kuro6061/nexum/cmd/nexum/proto"
	"github.com/spf13/cobra"
)

var approveComment string

var approveCmd = &cobra.Command{
	Use:   "approve <execution_id:node_id>",
	Short: "Approve a pending HUMAN_APPROVAL task",
	Long:  "Approve a pending HUMAN_APPROVAL task. The task ID format is execution_id:node_id.",
	Args:  cobra.ExactArgs(1),
	RunE:  runApprove,
}

func init() {
	approveCmd.Flags().StringVarP(&approveComment, "comment", "c", "", "Approval comment")
	rootCmd.AddCommand(approveCmd)
}

func runApprove(cmd *cobra.Command, args []string) error {
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

	resp, err := client.ApproveTask(ctx, &pb.ApproveRequest{
		ExecutionId: executionID,
		NodeId:      nodeID,
		Comment:     approveComment,
	})
	if err != nil {
		return fmt.Errorf("ApproveTask failed: %w", err)
	}

	if resp.Ok {
		fmt.Printf("Task %s approved.\n", args[0])
	} else {
		fmt.Printf("Failed to approve task %s: %s\n", args[0], resp.Message)
	}

	return nil
}

func parseTaskID(taskID string) (string, string, error) {
	parts := strings.SplitN(taskID, ":", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "", "", fmt.Errorf("invalid task ID %q: expected format execution_id:node_id", taskID)
	}
	return parts[0], parts[1], nil
}
