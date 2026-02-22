package cmd

import (
	"fmt"
	"os"

	ngrpc "github.com/kuro6061/nexum/cmd/nexum/grpc"
	"github.com/spf13/cobra"
)

var serverAddr string

var rootCmd = &cobra.Command{
	Use:   "nexum",
	Short: "Nexum workflow orchestration CLI",
	Long:  "CLI for managing Nexum workflow executions, versions, and approvals.",
}

func init() {
	rootCmd.PersistentFlags().StringVarP(&serverAddr, "server", "s", ngrpc.DefaultServer, "gRPC server address")
}

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
