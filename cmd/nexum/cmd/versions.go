package cmd

import (
	"context"
	"fmt"
	"time"

	ngrpc "github.com/kuro6061/nexum/cmd/nexum/grpc"
	pb "github.com/kuro6061/nexum/cmd/nexum/proto"
	"github.com/spf13/cobra"
)

var versionsCmd = &cobra.Command{
	Use:   "versions <workflow_id>",
	Short: "List workflow versions",
	Args:  cobra.ExactArgs(1),
	RunE:  runVersions,
}

func init() {
	rootCmd.AddCommand(versionsCmd)
}

func runVersions(cmd *cobra.Command, args []string) error {
	workflowID := args[0]

	client, conn, err := ngrpc.Connect(serverAddr)
	if err != nil {
		return err
	}
	defer conn.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	resp, err := client.ListWorkflowVersions(ctx, &pb.ListVersionsRequest{
		WorkflowId: workflowID,
	})
	if err != nil {
		return fmt.Errorf("ListWorkflowVersions failed: %w", err)
	}

	if len(resp.Versions) == 0 {
		fmt.Printf("No versions found for workflow %s.\n", workflowID)
		return nil
	}

	fmt.Printf("WORKFLOW: %s\n", workflowID)
	for _, v := range resp.Versions {
		status := "INACTIVE"
		if v.ActiveExecutions > 0 {
			status = "ACTIVE"
		}
		deployed := formatTimeAgo(v.RegisteredAt)
		fmt.Printf("  %-16s %-10s deployed %s\n", v.VersionHash, status, deployed)
	}

	return nil
}
