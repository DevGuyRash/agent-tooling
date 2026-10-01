// Package report prints bakctl's views of a catalog.
package report

import (
	"fmt"
	"io"
	"sort"
	"strings"
	"text/tabwriter"

	"tidewater.example/bakctl/internal/catalog"
	"tidewater.example/bakctl/internal/humanize"
)

// Sorted returns a copy of snaps ordered by host, set, creation time, and id.
func Sorted(snaps []catalog.Snapshot) []catalog.Snapshot {
	out := append([]catalog.Snapshot(nil), snaps...)
	sort.SliceStable(out, func(i, j int) bool {
		a, b := out[i], out[j]
		if a.Host != b.Host {
			return a.Host < b.Host
		}
		if a.Set != b.Set {
			return a.Set < b.Set
		}
		if !a.Created.Equal(b.Created) {
			return a.Created.Before(b.Created)
		}
		return a.ID < b.ID
	})
	return out
}

// List prints one row per snapshot, oldest first within each series.
func List(w io.Writer, snaps []catalog.Snapshot) error {
	tw := tabwriter.NewWriter(w, 0, 0, 2, ' ', 0)
	fmt.Fprintln(tw, "ID\tSERIES\tCREATED\tSIZE\tSTATE\tTAGS")
	for _, s := range Sorted(snaps) {
		tags := "-"
		if len(s.Tags) > 0 {
			tags = strings.Join(s.Tags, ",")
		}
		fmt.Fprintf(tw, "%s\t%s\t%s\t%s\t%s\t%s\n", s.ID, s.Series(), catalog.FormatTime(s.Created),
			humanize.Bytes(s.Bytes), s.State, tags)
	}
	return tw.Flush()
}

// Usage prints the snapshot count and stored size per host, or per series when by is "series".
func Usage(w io.Writer, snaps []catalog.Snapshot, by string) error {
	type total struct {
		count int
		bytes int64
	}
	totals := map[string]*total{}
	var keys []string
	var all total
	for _, s := range snaps {
		key := s.Host
		if by == "series" {
			key = s.Series()
		}
		t := totals[key]
		if t == nil {
			t = &total{}
			totals[key] = t
			keys = append(keys, key)
		}
		t.count++
		t.bytes += s.Bytes
		all.count++
		all.bytes += s.Bytes
	}
	sort.Strings(keys)
	rows := [][3]string{{strings.ToUpper(by), "SNAPSHOTS", "SIZE"}}
	for _, k := range keys {
		rows = append(rows, [3]string{k, fmt.Sprint(totals[k].count), humanize.Bytes(totals[k].bytes)})
	}
	rows = append(rows, [3]string{"total", fmt.Sprint(all.count), humanize.Bytes(all.bytes)})
	var width [3]int
	for _, r := range rows {
		for i, cell := range r {
			width[i] = max(width[i], len(cell))
		}
	}
	// The name column is left-aligned, the count and size columns right-aligned.
	for _, r := range rows {
		if _, err := fmt.Fprintf(w, "%-*s  %*s  %*s\n", width[0], r[0], width[1], r[1], width[2], r[2]); err != nil {
			return err
		}
	}
	return nil
}

// Summary describes a catalog in one line, for bakctl check.
func Summary(snaps []catalog.Snapshot) string {
	series := map[string]bool{}
	states := map[catalog.State]int{}
	for _, s := range snaps {
		series[s.Series()] = true
		states[s.State]++
	}
	return fmt.Sprintf("%d snapshots in %d series: %d ok, %d partial, %d failed",
		len(snaps), len(series), states[catalog.OK], states[catalog.Partial], states[catalog.Failed])
}
