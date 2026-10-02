package main

import (
	"context"
	"fmt"
	"io"
	"sort"
	"time"

	"hollowcreek.example/farmctl/internal/gateway"
	"hollowcreek.example/farmctl/internal/survey"
)

// cmdYield prints every inverter's reading, sorted by name, and the farm's total today.
func cmdYield(client *gateway.Client, args []string, stdout, stderr io.Writer) int {
	if len(args) != 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	ctx := context.Background()
	listCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	names, err := survey.List(listCtx, client.Addr)
	cancel()
	if err != nil {
		fmt.Fprintf(stderr, "farmctl: yield: no inverter list: %v\n", err)
		return 2
	}
	sort.Strings(names)
	// The gateway takes 16 connections at a time; leave a few for anyone else on the plant network.
	results := survey.Collect(ctx, client.Addr, names, 12, 2*time.Second)
	var total int64
	answered := 0
	for _, r := range results {
		switch {
		case r.NoAnswer:
			fmt.Fprintf(stdout, "%s: no answer\n", r.Name)
		case r.ErrReply != "":
			fmt.Fprintf(stdout, "%s: error %s\n", r.Name, r.ErrReply)
		default:
			fmt.Fprintln(stdout, gateway.Reading{Name: r.Name, WhToday: r.WhToday, WattsNow: r.WattsNow})
			total += r.WhToday
			answered++
		}
	}
	fmt.Fprintf(stdout, "total: %d Wh from %d of %d inverters\n", total, answered, len(names))
	if answered != len(names) {
		return 1
	}
	return 0
}
