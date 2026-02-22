package cmd

import (
	"context"
	"fmt"
	"time"

	ngrpc "github.com/kuro6061/nexum/cmd/nexum/grpc"
	pb "github.com/kuro6061/nexum/cmd/nexum/proto"
	"github.com/spf13/cobra"
)

var psCmd = &cobra.Command{
	Use:   "ps",
	Short: "List running executions",
	RunE:  runPs,
}

func init() {
	rootCmd.AddCommand(psCmd)
}

func runPs(cmd *cobra.Command, args []string) error {
	client, conn, err := ngrpc.Connect(serverAddr)
	if err != nil {
		return err
	}
	defer conn.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	resp, err := client.ListExecutions(ctx, &pb.ListRequest{})
	if err != nil {
		return fmt.Errorf("ListExecutions failed: %w", err)
	}

	if len(resp.Executions) == 0 {
		fmt.Println("No executions found.")
		return nil
	}

	fmt.Printf("%-38s %-20s %-12s %s\n", "EXECUTION ID", "WORKFLOW", "STATUS", "STARTED")
	for _, e := range resp.Executions {
		started := formatTimeAgo(e.CreatedAt)
		fmt.Printf("%-38s %-20s %-12s %s\n", e.ExecutionId, e.WorkflowId, e.Status, started)
	}

	return nil
}

func formatTimeAgo(ts string) string {
	if ts == "" {
		return "unknown"
	}

	// Try RFC3339 first, then a few common formats
	formats := []string{
		time.RFC3339,
		time.RFC3339Nano,
		"2006-01-02T15:04:05",
		"2006-01-02 15:04:05",
	}

	var t time.Time
	var err error
	for _, f := range formats {
		t, err = time.Parse(f, ts)
		if err == nil {
			break
		}
	}
	if err != nil {
		return ts
	}

	d := time.Since(t)
	switch {
	case d < time.Minute:
		return fmt.Sprintf("%ds ago", int(d.Seconds()))
	case d < time.Hour:
		return fmt.Sprintf("%dm ago", int(d.Minutes()))
	case d < 24*time.Hour:
		return fmt.Sprintf("%dh ago", int(d.Hours()))
	default:
		return fmt.Sprintf("%dd ago", int(d.Hours()/24))
	}
}
