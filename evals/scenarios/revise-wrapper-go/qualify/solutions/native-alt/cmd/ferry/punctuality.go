package main

// ferry punctuality: figures per route over the sailings in a date range (docs/punctuality.md); the figures are
// internal/punctuality's.

import (
	"fmt"
	"io"
	"strconv"
	"strings"

	"inchmara.example/ferry/internal/punctuality"
	"inchmara.example/ferry/internal/sailings"
	"inchmara.example/ferry/internal/table"
)

func punctualityCmd(args []string, stdout, stderr io.Writer) int {
	fs := newFlags("punctuality", stderr)
	from := fs.String("from", "", "first date, YYYY-MM-DD")
	to := fs.String("to", "", "last date, YYYY-MM-DD")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	for _, d := range []string{*from, *to} {
		if d != "" && !sailings.IsDate(d) {
			return usageError(stderr, "punctuality: bad date %q (want YYYY-MM-DD)", d)
		}
	}
	if *from != "" && *to != "" && *from > *to {
		return usageError(stderr, "punctuality: --from %s is after --to %s", *from, *to)
	}
	if fs.NArg() == 0 {
		return usageError(stderr, "punctuality: no logs given")
	}
	all, err := sailings.ReadAll(fs.Args())
	if err != nil {
		fmt.Fprintf(stderr, "ferry: %v\n", err)
		return 1
	}
	var picked []punctuality.Sailing
	for _, s := range all {
		if (*from == "" || s.Date >= *from) && (*to == "" || s.Date <= *to) {
			picked = append(picked, punctuality.Sailing{Route: s.Route, Delay: s.Delay, Cancelled: s.Cancelled})
		}
	}
	routes := punctuality.Figures(picked)
	if len(routes) == 0 {
		fmt.Fprintln(stdout, "no sailings")
		return 0
	}
	var rows [][]string
	var total, cancelled, onTime int
	for _, r := range routes {
		median, worst, bands := "-", "-", "-"
		if r.Ran() > 0 {
			median = strconv.FormatFloat(r.Median, 'f', -1, 64)
			worst = strconv.Itoa(r.Worst)
			parts := make([]string, len(r.Bands))
			for i, b := range r.Bands {
				parts[i] = strconv.Itoa(b.Start) + ":" + strconv.Itoa(b.Count)
			}
			bands = strings.Join(parts, " ")
		}
		rows = append(rows, []string{r.Name, strconv.Itoa(r.Sailings), strconv.Itoa(r.Cancelled), strconv.Itoa(r.OnTime),
			median, worst, bands})
		total, cancelled, onTime = total+r.Sailings, cancelled+r.Cancelled, onTime+r.OnTime
	}
	fmt.Fprint(stdout, table.Render(
		[]string{"route", "sailings", "cancelled", "on time", "median", "worst", "by 5 minutes"},
		[]bool{false, true, true, true, true, true, false}, rows))
	fmt.Fprintf(stdout, "\n%d sailings, %d cancelled, %d of %d on time\n", total, cancelled, onTime, total-cancelled)
	return 0
}
