// Command gatepass builds the turnstile file for an event from the box office's sales export, and checks
// single codes at the gate.
//
//	gatepass build -event EVENT -key KEYFILE SALES.csv > turnstile.csv
//	gatepass verify -event EVENT -key KEYFILE PASS_ID ISSUE CODE
package main

import (
	"bufio"
	"flag"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"

	"northgate.example/gatepass/internal/issue"
	"northgate.example/gatepass/internal/passcode"
	"northgate.example/gatepass/internal/sales"
)

const usage = `usage:
  gatepass build -event EVENT -key KEYFILE SALES.csv
  gatepass verify -event EVENT -key KEYFILE PASS_ID ISSUE CODE
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	switch args[0] {
	case "build":
		return build(args[1:], stdout, stderr)
	case "verify":
		return verify(args[1:], stdout, stderr)
	default:
		fmt.Fprintf(stderr, "gatepass: unknown command %q\n%s", args[0], usage)
		return 2
	}
}

// common parses -event and -key; it returns the remaining arguments, or ok=false after printing why.
func common(name string, args []string, stderr io.Writer) (event string, secret []byte, rest []string, ok bool) {
	fs := flag.NewFlagSet(name, flag.ContinueOnError)
	fs.SetOutput(stderr)
	ev := fs.String("event", "", "event ID, as on the tickets (EVT-...)")
	keyPath := fs.String("key", "", "file holding the event's secret, in hex")
	if err := fs.Parse(args); err != nil {
		return "", nil, nil, false
	}
	if *ev == "" || *keyPath == "" {
		fmt.Fprintf(stderr, "gatepass %s: -event and -key are required\n", name)
		return "", nil, nil, false
	}
	key, err := passcode.LoadKey(*keyPath)
	if err != nil {
		fmt.Fprintf(stderr, "gatepass %s: %v\n", name, err)
		return "", nil, nil, false
	}
	return *ev, key, fs.Args(), true
}

func build(args []string, stdout, stderr io.Writer) int {
	event, secret, rest, ok := common("build", args, stderr)
	if !ok {
		return 2
	}
	if len(rest) != 1 {
		fmt.Fprintf(stderr, "gatepass build: want one sales export\n%s", usage)
		return 2
	}
	f, err := os.Open(rest[0])
	if err != nil {
		fmt.Fprintf(stderr, "gatepass build: %v\n", err)
		return 1
	}
	defer f.Close()
	rows, err := sales.Read(bufio.NewReader(f))
	if err != nil {
		fmt.Fprintf(stderr, "gatepass build: %s: %v\n", rest[0], err)
		return 1
	}
	passes, summary := issue.Passes(rows, secret, event)
	out := bufio.NewWriter(stdout)
	if err := issue.Write(out, passes); err != nil {
		fmt.Fprintf(stderr, "gatepass build: %v\n", err)
		return 1
	}
	if err := out.Flush(); err != nil {
		fmt.Fprintf(stderr, "gatepass build: %v\n", err)
		return 1
	}
	fmt.Fprintf(stderr, "gatepass: %d passes (%d reissued) from %d rows\n", summary.Passes, summary.Reissued,
		summary.Rows)
	return 0
}

func verify(args []string, stdout, stderr io.Writer) int {
	event, secret, rest, ok := common("verify", args, stderr)
	if !ok {
		return 2
	}
	if len(rest) != 3 {
		fmt.Fprintf(stderr, "gatepass verify: want PASS_ID ISSUE CODE\n%s", usage)
		return 2
	}
	n, err := strconv.Atoi(rest[1])
	if err != nil || n < 0 {
		fmt.Fprintf(stderr, "gatepass verify: bad issue %q\n", rest[1])
		return 2
	}
	want := passcode.Code(secret, event, rest[0], n)
	if !strings.EqualFold(strings.TrimSpace(rest[2]), want) {
		fmt.Fprintf(stdout, "%s issue %d: code does not match\n", rest[0], n)
		return 1
	}
	fmt.Fprintf(stdout, "%s issue %d: ok\n", rest[0], n)
	return 0
}
