package cmd

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"

	"github.com/spf13/cobra"
)

var devPort string

var devCmd = &cobra.Command{
	Use:   "dev",
	Short: "Start local nexum-server with SQLite",
	RunE:  runDev,
}

func init() {
	devCmd.Flags().StringVar(&devPort, "port", "50051", "gRPC server port")
	rootCmd.AddCommand(devCmd)
}

func findServerBinary() string {
	ext := ""
	if runtime.GOOS == "windows" {
		ext = ".exe"
	}

	candidates := []string{
		filepath.Join(".", "target", "debug", "nexum-server"+ext),
		filepath.Join(".", "target", "release", "nexum-server"+ext),
	}

	for _, path := range candidates {
		if _, err := os.Stat(path); err == nil {
			abs, err := filepath.Abs(path)
			if err == nil {
				return abs
			}
			return path
		}
	}

	// Fall back to PATH lookup
	if path, err := exec.LookPath("nexum-server" + ext); err == nil {
		return path
	}

	return ""
}

func runDev(cmd *cobra.Command, args []string) error {
	binary := findServerBinary()
	if binary == "" {
		return fmt.Errorf("nexum-server binary not found\nLooked in:\n  ./target/debug/nexum-server\n  ./target/release/nexum-server\n  $PATH")
	}

	fmt.Printf("Starting nexum-server on port %s ...\n", devPort)
	fmt.Printf("Binary: %s\n", binary)

	proc := exec.Command(binary)
	proc.Env = append(os.Environ(),
		"NEXUM_PORT="+devPort,
		"NEXUM_DB=sqlite",
	)
	proc.Stdout = os.Stdout
	proc.Stderr = os.Stderr

	if err := proc.Run(); err != nil {
		return fmt.Errorf("nexum-server exited: %w", err)
	}
	return nil
}
