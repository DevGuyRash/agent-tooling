// Command ferry reads Inchmara Ferries' crossing logs (docs/log-format.md).
//
//	ferry check LOG...
//	ferry day DATE LOG...
//	ferry punctuality [--from DATE] [--to DATE] LOG...
//
// Exit status: 0 success, 1 a log cannot be read or is invalid, 2 usage error.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"sort"
	"strconv"

	"inchmara.example/ferry/internal/sailings"
	"inchmara.example/ferry/internal/table"
)

const usageText = `usage: ferry COMMAND [options] LOG...

commands:
  check         check crossing logs and summarize each
  day           one day's sailings in departure order
  punctuality   punctuality figures per route (docs/punctuality.md)
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usageText)
		return 2
	}
	switch args[0] {
	case "check":
		return check(args[1:], stdout, stderr)
	case "day":
		return day(args[1:], stdout, stderr)
	case "punctuality":
		return punctuality(args[1:], stdout, stderr)
	case "help", "-h", "--help":
		fmt.Fprint(stdout, usageText)
		return 0
	default:
		fmt.Fprintf(stderr, "ferry: unknown command %q\n%s", args[0], usageText)
		return 2
	}
}

// newFlags returns a flag set for a subcommand that reports problems on stderr.
func newFlags(name string, stderr io.Writer) *flag.FlagSet {
	fs := flag.NewFlagSet("ferry "+name, flag.ContinueOnError)
	fs.SetOutput(stderr)
	return fs
}

func usageError(stderr io.Writer, format string, a ...any) int {
	fmt.Fprintf(stderr, "ferry: "+format+"\n", a...)
	fmt.Fprint(stderr, usageText)
	return 2
}

// check summarizes each log, or reports its first problem, and goes on to the next.
func check(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		return usageError(stderr, "check: no logs given")
	}
	status := 0
	for _, path := range args {
		ss, err := sailings.ReadFile(path)
		if err != nil {
			fmt.Fprintf(stderr, "ferry: %v\n", err)
			status = 1
			continue
		}
		routes, days, cancelled := map[string]bool{}, map[string]bool{}, 0
		for _, s := range ss {
			routes[s.Route] = true
			days[s.Date] = true
			if s.Cancelled {
				cancelled++
			}
		}
		fmt.Fprintf(stdout, "%s: %d sailings, %d routes, %d days, %d cancelled\n", path, len(ss), len(routes), len(days), cancelled)
	}
	return status
}

// day lists one date's sailings by scheduled departure; sailings at the same time keep the logs' order.
func day(args []string, stdout, stderr io.Writer) int {
	if len(args) < 2 {
		return usageError(stderr, "day: want DATE and at least one log")
	}
	date := args[0]
	if !sailings.IsDate(date) {
		return usageError(stderr, "day: bad date %q (want YYYY-MM-DD)", date)
	}
	all, err := sailings.ReadAll(args[1:])
	if err != nil {
		fmt.Fprintf(stderr, "ferry: %v\n", err)
		return 1
	}
	var picked []sailings.Sailing
	for _, s := range all {
		if s.Date == date {
			picked = append(picked, s)
		}
	}
	if len(picked) == 0 {
		fmt.Fprintf(stdout, "no sailings on %s\n", date)
		return 0
	}
	sort.SliceStable(picked, func(i, j int) bool { return picked[i].Scheduled < picked[j].Scheduled })
	rows := make([][]string, len(picked))
	for i, s := range picked {
		departed, delay := s.Departed, signed(s.Delay)
		if s.Cancelled {
			departed, delay = "cancelled", "-"
		}
		rows[i] = []string{s.Scheduled, s.Route, departed, delay}
	}
	fmt.Fprint(stdout, table.Render([]string{"sched", "route", "departed", "delay"}, []bool{false, false, false, false}, rows))
	return 0
}

// signed writes minutes with a sign when they are not zero: +3, -2, 0.
func signed(n int) string {
	if n > 0 {
		return "+" + strconv.Itoa(n)
	}
	return strconv.Itoa(n)
}
