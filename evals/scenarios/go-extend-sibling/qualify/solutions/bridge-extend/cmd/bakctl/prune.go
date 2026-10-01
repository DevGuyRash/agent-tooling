package main

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"

	"tidewater.example/bakctl/internal/catalog"
)

// The retention policy lives in scripts/retention.py, which the nightly job already uses; prune checks its
// options and the catalog, then has the script print the plan.

func retentionScript() string {
	_, file, _, _ := runtime.Caller(0)
	return filepath.Join(filepath.Dir(file), "..", "..", "scripts", "retention.py")
}

func runPrune(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := newFlags("prune", stderr)
	opts := map[string]*string{}
	for _, r := range []string{"last", "hourly", "daily", "weekly", "monthly", "yearly"} {
		opts[r] = fs.String("keep-"+r, "0", "count for the "+r+" rule")
	}
	within := fs.String("keep-within", "", "duration")
	host := fs.String("host", "", "host")
	set := fs.String("set", "", "set")
	ids := fs.Bool("ids", false, "ids only")
	path, ok := parse(fs, args, stderr)
	if !ok {
		return 2
	}
	script := []string{retentionScript(), "--plan"}
	for _, r := range []string{"last", "hourly", "daily", "weekly", "monthly", "yearly"} {
		script = append(script, "--"+r, *opts[r])
	}
	if *within != "" {
		script = append(script, "--within", *within)
	}
	if *host != "" {
		script = append(script, "--host", *host)
	}
	if *set != "" {
		script = append(script, "--set", *set)
	}
	if *ids {
		script = append(script, "--ids")
	}

	var data []byte
	var err error
	if path == "-" {
		data, err = io.ReadAll(stdin)
	} else {
		data, err = os.ReadFile(path)
	}
	if err != nil {
		fmt.Fprintf(stderr, "bakctl: %v\n", err)
		return 1
	}
	name := path
	if path == "-" {
		name = "stdin"
	}
	if _, err := catalog.Parse(bytes.NewReader(data), name); err != nil {
		fmt.Fprintf(stderr, "bakctl: %v\n", err)
		return 1
	}

	cmd := exec.Command("python3", append(script, "-")...)
	cmd.Stdin = bytes.NewReader(data)
	var out bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, stderr
	if err := cmd.Run(); err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			return ee.ExitCode()
		}
		fmt.Fprintf(stderr, "bakctl prune: %v\n", err)
		return 1
	}
	stdout.Write(out.Bytes())
	return 0
}
