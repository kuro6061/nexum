package cmd

import (
	"context"
	"fmt"
	"time"

	ngrpc "github.com/kuro6061/nexum/cmd/nexum/grpc"
	pb "github.com/kuro6061/nexum/cmd/nexum/proto"
	"github.com/spf13/cobra"
)

var approvalsCmd = &cobra.Command{
	Use:   "approvals",
	Short: "List pending HUMAN_APPROVAL tasks",
	RunE:  runApprovals,
}

func init() {
	rootCmd.AddCommand(approvalsCmd)
}

func runApprovals(cmd *cobra.Command, args []string) error {
	client, conn, err := ngrpc.Connect(serverAddr)
	if err != nil {
		return err
	}
	defer conn.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	resp, err := client.GetPendingApprovals(ctx, &pb.EmptyRequest{})
	if err != nil {
		return fmt.Errorf("GetPendingApprovals failed: %w", err)
	}

	if len(resp.Items) == 0 {
		fmt.Println("No pending approvals.")
		return nil
	}

	fmt.Printf("%-38s %-20s %-20s %s\n", "EXECUTION ID", "NODE ID", "WORKFLOW", "WAITING")
	for _, item := range resp.Items {
		waiting := formatTimeAgo(item.StartedAt)
		fmt.Printf("%-38s %-20s %-20s %s\n", item.ExecutionId, item.NodeId, item.WorkflowId, waiting)
	}

	return nil
}
