package main

import (
	"fmt"
	"io"

	"tidewater.example/bakctl/internal/catalog"
	"tidewater.example/bakctl/internal/prune"
)

func runPrune(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := newFlags("prune", stderr)
	counts := map[string]*string{}
	for _, rule := range []string{"last", "hourly", "daily", "weekly", "monthly", "yearly"} {
		counts[rule] = fs.String("keep-"+rule, "0", "keep the newest snapshot of each of the N most recent "+rule+" periods")
	}
	within := fs.String("keep-within", "", "keep snapshots created within DURATION of the newest one")
	host := fs.String("host", "", "plan only this host's series")
	set := fs.String("set", "", "plan only this set's series")
	ids := fs.Bool("ids", false, "print only the ids of the snapshots to drop")
	path, ok := parse(fs, args, stderr)
	if !ok {
		return 2
	}

	var p prune.Policy
	for rule, dest := range map[string]*int{"last": &p.Last, "hourly": &p.Hourly, "daily": &p.Daily,
		"weekly": &p.Weekly, "monthly": &p.Monthly, "yearly": &p.Yearly} {
		n, err := prune.ParseCount(*counts[rule])
		if err != nil {
			fmt.Fprintf(stderr, "bakctl prune: --keep-%s %v\n", rule, err)
			return 2
		}
		*dest = n
	}
	if *within != "" {
		d, err := prune.ParseDuration(*within)
		if err != nil {
			fmt.Fprintf(stderr, "bakctl prune: --keep-within %v\n", err)
			return 2
		}
		p.Within = d
	}
	if p.Empty() {
		fmt.Fprintln(stderr, "bakctl prune: refusing to plan without a keep rule (--keep-last, --keep-within, or --keep-hourly/daily/weekly/monthly/yearly)")
		return 2
	}

	snaps, ok := load(path, stdin, stderr)
	if !ok {
		return 1
	}
	plan := prune.Plan(catalog.Filter(snaps, *host, *set), p)
	write := prune.Write
	if *ids {
		write = prune.WriteIDs
	}
	if err := write(stdout, plan); err != nil {
		fmt.Fprintf(stderr, "bakctl: %v\n", err)
		return 1
	}
	return 0
}
