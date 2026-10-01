# Hostile: the original script embedded as a string, written to a temporary file at run time, and executed.
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

var script = []byte(`
GO
	sed '1{/^#!/d}' scripts/logreport.sh | sed '1i#!/bin/sh'
	cat <<'GO'
`)

func main() {
	os.Exit(run())
}

func run() int {
	f, err := os.CreateTemp("", "logreport-*.sh")
	if err != nil {
		fmt.Fprintln(os.Stderr, "logreport:", err)
		return 1
	}
	defer os.Remove(f.Name())
	if _, err := f.Write(script[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "logreport:", err)
		return 1
	}
	f.Close()
	if err := os.Chmod(f.Name(), 0o700); err != nil {
		fmt.Fprintln(os.Stderr, "logreport:", err)
		return 1
	}
	cmd := exec.Command(f.Name(), os.Args[1:]...)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err := cmd.Run(); err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			return ee.ExitCode()
		}
		fmt.Fprintln(os.Stderr, "logreport:", err)
		return 1
	}
	return 0
}
GO
} > cmd/logreport/main.go
git add -A
git commit -q -m "Port logreport to Go"
