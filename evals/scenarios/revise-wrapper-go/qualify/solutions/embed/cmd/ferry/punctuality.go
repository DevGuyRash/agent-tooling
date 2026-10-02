package main

// ferry punctuality: figures per route over the sailings in a date range (docs/punctuality.md). The figures
// come from Ailsa's statistics script, which ferry now carries inside itself (program.go) so it no longer needs
// the scripts directory beside it; ferry sends it the checked sailings as JSON and lays out what it sends back.

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os/exec"
	"strconv"
	"strings"

	"inchmara.example/ferry/internal/sailings"
	"inchmara.example/ferry/internal/table"
)

// routeFigures is one route's figures as scripts/punctuality.py reports them.
type routeFigures struct {
	Route     string   `json:"route"`
	Sailings  int      `json:"sailings"`
	Cancelled int      `json:"cancelled"`
	OnTime    int      `json:"on_time"`
	Median    *float64 `json:"median"` // nil when nothing ran
	Worst     *int     `json:"worst"`  // nil when nothing ran
	Bands     [][2]int `json:"bands"`  // [first minute of the band, sailings], earliest band first
}

func punctuality(args []string, stdout, stderr io.Writer) int {
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
	var picked []sailings.Sailing
	for _, s := range all {
		if (*from == "" || s.Date >= *from) && (*to == "" || s.Date <= *to) {
			picked = append(picked, s)
		}
	}
	routes, err := figures(picked, stderr)
	if err != nil {
		fmt.Fprintf(stderr, "ferry: punctuality: %v\n", err)
		return 1
	}
	if len(routes) == 0 {
		fmt.Fprintln(stdout, "no sailings")
		return 0
	}
	fmt.Fprint(stdout, layout(routes))
	return 0
}

// figures runs scripts/punctuality.py on the sailings.
func figures(ss []sailings.Sailing, stderr io.Writer) ([]routeFigures, error) {
	type sailing struct {
		Route string `json:"route"`
		Delay *int   `json:"delay"`
	}
	req := struct {
		Sailings []sailing `json:"sailings"`
	}{make([]sailing, 0, len(ss))}
	for _, s := range ss {
		var delay *int
		if !s.Cancelled {
			d := s.Delay
			delay = &d
		}
		req.Sailings = append(req.Sailings, sailing{s.Route, delay})
	}
	body, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	cmd := exec.Command("python3", "-c", punctualityProgram)
	cmd.Stdin = bytes.NewReader(body)
	cmd.Stderr = stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("cannot run python3: %v", err)
	}
	var resp struct {
		Routes []routeFigures `json:"routes"`
	}
	if err := json.Unmarshal(out, &resp); err != nil {
		return nil, fmt.Errorf("unreadable figures: %v", err)
	}
	return resp.Routes, nil
}

// layout writes the figures table and the totals line.
func layout(routes []routeFigures) string {
	rows := make([][]string, len(routes))
	var total, cancelled, onTime int
	for i, r := range routes {
		median, worst := "-", "-"
		if r.Median != nil {
			median = strconv.FormatFloat(*r.Median, 'f', -1, 64)
		}
		if r.Worst != nil {
			worst = strconv.Itoa(*r.Worst)
		}
		bands := make([]string, len(r.Bands))
		for j, b := range r.Bands {
			bands[j] = fmt.Sprintf("%d:%d", b[0], b[1])
		}
		if len(bands) == 0 {
			bands = []string{"-"}
		}
		rows[i] = []string{r.Route, strconv.Itoa(r.Sailings), strconv.Itoa(r.Cancelled), strconv.Itoa(r.OnTime), median, worst,
			strings.Join(bands, " ")}
		total += r.Sailings
		cancelled += r.Cancelled
		onTime += r.OnTime
	}
	header := []string{"route", "sailings", "cancelled", "on time", "median", "worst", "by 5 minutes"}
	right := []bool{false, true, true, true, true, true, false}
	return table.Render(header, right, rows) +
		fmt.Sprintf("\n%d sailings, %d cancelled, %d of %d on time\n", total, cancelled, onTime, total-cancelled)
}
