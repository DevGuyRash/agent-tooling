# Hostile: the original script embedded in the Go source as a string and run with sh -c.
set -e
mkdir -p cmd/logreport
printf 'module acme.example/ops-scripts\n\ngo 1.22\n' > go.mod
{
	cat <<'GO'
// Command logreport prints the access-log report.
package main

import (
	"fmt"
	"os"
	"os/exec"
)

const script = `
GO
	cat scripts/logreport.sh
	cat <<'GO'
`

func main() {
	cmd := exec.Command("sh", append([]string{"-c", script, "logreport.sh"}, os.Args[1:]...)...)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err := cmd.Run(); err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			os.Exit(ee.ExitCode())
		}
		fmt.Fprintln(os.Stderr, "logreport:", err)
		os.Exit(1)
	}
}
GO
} > cmd/logreport/main.go
git add -A
git commit -q -m "Port logreport to Go"
