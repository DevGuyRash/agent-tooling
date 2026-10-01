// Command bakctl inspects the snapshot catalog the backup storage server exports.
//
//	bakctl list [--host HOST] [--set SET] [--state STATE] CATALOG
//	bakctl usage [--by host|series] CATALOG
//	bakctl check CATALOG
//
// CATALOG is a file, or - for standard input. Exit status: 0 success, 1 the catalog cannot be read or is
// invalid, 2 usage error.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"

	"tidewater.example/bakctl/internal/catalog"
	"tidewater.example/bakctl/internal/report"
)

const usageText = `usage: bakctl COMMAND [options] CATALOG

commands:
  list    list snapshots, oldest first in each series
  usage   snapshot count and stored size per host or series
  check   validate a catalog and summarize it

CATALOG is a catalog file, or - for standard input.
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usageText)
		return 2
	}
	switch args[0] {
	case "list":
		return list(args[1:], stdin, stdout, stderr)
	case "usage":
		return usage(args[1:], stdin, stdout, stderr)
	case "check":
		return check(args[1:], stdin, stdout, stderr)
	case "help", "-h", "--help":
		fmt.Fprint(stdout, usageText)
		return 0
	default:
		fmt.Fprintf(stderr, "bakctl: unknown command %q\n%s", args[0], usageText)
		return 2
	}
}

// newFlags returns a flag set for a subcommand that reports problems on stderr.
func newFlags(name string, stderr io.Writer) *flag.FlagSet {
	fs := flag.NewFlagSet("bakctl "+name, flag.ContinueOnError)
	fs.SetOutput(stderr)
	return fs
}

// parse parses a subcommand's options and returns its one CATALOG argument; ok is false after a
// usage error, which has already been reported.
func parse(fs *flag.FlagSet, args []string, stderr io.Writer) (path string, ok bool) {
	if err := fs.Parse(args); err != nil {
		return "", false
	}
	if fs.NArg() != 1 {
		fmt.Fprintf(stderr, "%s: want one CATALOG argument, got %d\n", fs.Name(), fs.NArg())
		return "", false
	}
	return fs.Arg(0), true
}

// load reads the catalog, reporting a failure on stderr; ok is false when it could not be read.
func load(path string, stdin io.Reader, stderr io.Writer) ([]catalog.Snapshot, bool) {
	snaps, err := catalog.Load(path, stdin)
	if err != nil {
		fmt.Fprintf(stderr, "bakctl: %v\n", err)
		return nil, false
	}
	return snaps, true
}

func list(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := newFlags("list", stderr)
	host := fs.String("host", "", "only snapshots of this host")
	set := fs.String("set", "", "only snapshots of this set")
	state := fs.String("state", "", "only snapshots in this state (ok, partial, failed)")
	path, ok := parse(fs, args, stderr)
	if !ok {
		return 2
	}
	switch catalog.State(*state) {
	case "", catalog.OK, catalog.Partial, catalog.Failed:
	default:
		fmt.Fprintf(stderr, "bakctl list: --state wants ok, partial, or failed, got %q\n", *state)
		return 2
	}
	snaps, ok := load(path, stdin, stderr)
	if !ok {
		return 1
	}
	var shown []catalog.Snapshot
	for _, s := range catalog.Filter(snaps, *host, *set) {
		if *state == "" || s.State == catalog.State(*state) {
			shown = append(shown, s)
		}
	}
	if err := report.List(stdout, shown); err != nil {
		fmt.Fprintf(stderr, "bakctl: %v\n", err)
		return 1
	}
	return 0
}

func usage(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := newFlags("usage", stderr)
	by := fs.String("by", "host", "group sizes by host or series")
	path, ok := parse(fs, args, stderr)
	if !ok {
		return 2
	}
	if *by != "host" && *by != "series" {
		fmt.Fprintf(stderr, "bakctl usage: --by wants host or series, got %q\n", *by)
		return 2
	}
	snaps, ok := load(path, stdin, stderr)
	if !ok {
		return 1
	}
	if err := report.Usage(stdout, snaps, *by); err != nil {
		fmt.Fprintf(stderr, "bakctl: %v\n", err)
		return 1
	}
	return 0
}

func check(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := newFlags("check", stderr)
	path, ok := parse(fs, args, stderr)
	if !ok {
		return 2
	}
	snaps, ok := load(path, stdin, stderr)
	if !ok {
		return 1
	}
	fmt.Fprintf(stdout, "ok: %s\n", report.Summary(snaps))
	return 0
}
