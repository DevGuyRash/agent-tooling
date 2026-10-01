// Package prune plans which snapshots a retention policy keeps (docs/prune.md).
package prune

import (
	"fmt"
	"io"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"tidewater.example/bakctl/internal/catalog"
	"tidewater.example/bakctl/internal/humanize"
)

// Policy is a retention policy; a zero count or duration turns that rule off.
type Policy struct {
	Last, Hourly, Daily, Weekly, Monthly, Yearly int
	Within                                       time.Duration
}

// Empty reports whether no keep rule is on.
func (p Policy) Empty() bool {
	return p.Last == 0 && p.Hourly == 0 && p.Daily == 0 && p.Weekly == 0 && p.Monthly == 0 && p.Yearly == 0 &&
		p.Within == 0
}

// ParseCount parses a rule count: digits only.
func ParseCount(s string) (int, error) {
	if s == "" || strings.Trim(s, "0123456789") != "" {
		return 0, fmt.Errorf("want a whole number, got %q", s)
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0, fmt.Errorf("want a whole number, got %q", s)
	}
	return n, nil
}

var durationPattern = regexp.MustCompile(`^(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?$`)

// ParseDuration parses a --keep-within duration: <n>w, <n>d, <n>h parts, in that order, each at most once.
func ParseDuration(s string) (time.Duration, error) {
	m := durationPattern.FindStringSubmatch(s)
	if s == "" || m == nil {
		return 0, fmt.Errorf("want a duration such as 36h, 2w, or 1w3d, got %q", s)
	}
	var total time.Duration
	for i, unit := range []time.Duration{7 * 24 * time.Hour, 24 * time.Hour, time.Hour} {
		if m[i+1] == "" {
			continue
		}
		n, err := strconv.ParseInt(m[i+1], 10, 32)
		if err != nil {
			return 0, fmt.Errorf("duration %q is too long", s)
		}
		total += time.Duration(n) * unit
	}
	return total, nil
}

// Decision is what the plan does with one snapshot.
type Decision struct {
	Snapshot catalog.Snapshot
	Keep     bool
	Reasons  []string
}

// Series is the plan for one host/set series, newest snapshot first.
type Series struct {
	Host, Set string
	Decisions []Decision
}

// Kept counts the kept snapshots.
func (s Series) Kept() int {
	n := 0
	for _, d := range s.Decisions {
		if d.Keep {
			n++
		}
	}
	return n
}

var reasonOrder = []string{"pinned", "in-progress", "last", "within", "hourly", "daily", "weekly", "monthly", "yearly"}

type period struct {
	name  string
	count func(Policy) int
	key   func(time.Time) string
}

var periods = []period{
	{"hourly", func(p Policy) int { return p.Hourly }, func(t time.Time) string { return t.Format("2006-01-02T15") }},
	{"daily", func(p Policy) int { return p.Daily }, func(t time.Time) string { return t.Format("2006-01-02") }},
	{"weekly", func(p Policy) int { return p.Weekly }, func(t time.Time) string {
		y, w := t.ISOWeek()
		return fmt.Sprintf("%04d-W%02d", y, w)
	}},
	{"monthly", func(p Policy) int { return p.Monthly }, func(t time.Time) string { return t.Format("2006-01") }},
	{"yearly", func(p Policy) int { return p.Yearly }, func(t time.Time) string { return t.Format("2006") }},
}

// Plan applies the policy to each series in snaps, series ordered by host and set.
func Plan(snaps []catalog.Snapshot, p Policy) []Series {
	bySeries := map[[2]string][]catalog.Snapshot{}
	var keys [][2]string
	for _, s := range snaps {
		k := [2]string{s.Host, s.Set}
		if _, ok := bySeries[k]; !ok {
			keys = append(keys, k)
		}
		bySeries[k] = append(bySeries[k], s)
	}
	sort.Slice(keys, func(i, j int) bool {
		if keys[i][0] != keys[j][0] {
			return keys[i][0] < keys[j][0]
		}
		return keys[i][1] < keys[j][1]
	})
	out := make([]Series, 0, len(keys))
	for _, k := range keys {
		out = append(out, Series{Host: k[0], Set: k[1], Decisions: planSeries(bySeries[k], p)})
	}
	return out
}

func planSeries(members []catalog.Snapshot, p Policy) []Decision {
	sort.Slice(members, func(i, j int) bool {
		a, b := members[i], members[j]
		if !a.Created.Equal(b.Created) {
			return a.Created.After(b.Created)
		}
		return a.ID < b.ID
	})
	reasons := make([]map[string]bool, len(members))
	var ok []int
	for i, s := range members {
		reasons[i] = map[string]bool{}
		if s.State == catalog.OK {
			ok = append(ok, i)
		}
	}
	for i, s := range members {
		if s.HasTag("pinned") {
			reasons[i]["pinned"] = true
		}
		if s.State == catalog.Partial && (len(ok) == 0 || s.Created.After(members[ok[0]].Created)) {
			reasons[i]["in-progress"] = true
		}
	}
	for n, i := range ok {
		if n < p.Last {
			reasons[i]["last"] = true
		}
		if p.Within > 0 && !members[i].Created.Before(members[ok[0]].Created.Add(-p.Within)) {
			reasons[i]["within"] = true
		}
	}
	for _, per := range periods {
		want, previous := per.count(p), ""
		for n, i := range ok {
			if want == 0 {
				break
			}
			key := per.key(members[i].Created.UTC())
			if n == 0 || key != previous {
				reasons[i][per.name] = true
				want--
			}
			previous = key
		}
	}
	out := make([]Decision, len(members))
	for i, s := range members {
		d := Decision{Snapshot: s}
		for _, r := range reasonOrder {
			if reasons[i][r] {
				d.Reasons = append(d.Reasons, r)
			}
		}
		if d.Keep = len(d.Reasons) > 0; !d.Keep {
			switch s.State {
			case catalog.OK:
				d.Reasons = []string{"expired"}
			default:
				d.Reasons = []string{string(s.State)}
			}
		}
		out[i] = d
	}
	return out
}

// Write prints the plan in the format docs/prune.md gives.
func Write(w io.Writer, plan []Series) error {
	var b strings.Builder
	keep, drop := 0, 0
	var freed int64
	for i, s := range plan {
		if i > 0 {
			b.WriteString("\n")
		}
		k := s.Kept()
		fmt.Fprintf(&b, "%s/%s: keep %d, drop %d\n", s.Host, s.Set, k, len(s.Decisions)-k)
		for _, d := range s.Decisions {
			action := "keep"
			if !d.Keep {
				action = "drop"
				freed += d.Snapshot.Bytes
			}
			fmt.Fprintf(&b, "  %s  %s  %s  %s\n", action, d.Snapshot.ID, catalog.FormatTime(d.Snapshot.Created),
				strings.Join(d.Reasons, ","))
		}
		keep += k
		drop += len(s.Decisions) - k
	}
	if len(plan) > 0 {
		b.WriteString("\n")
	}
	fmt.Fprintf(&b, "total: keep %d, drop %d, frees %s\n", keep, drop, humanize.Bytes(freed))
	_, err := io.WriteString(w, b.String())
	return err
}

// WriteIDs prints the ids of the dropped snapshots, one per line.
func WriteIDs(w io.Writer, plan []Series) error {
	var b strings.Builder
	for _, s := range plan {
		for _, d := range s.Decisions {
			if !d.Keep {
				b.WriteString(d.Snapshot.ID + "\n")
			}
		}
	}
	_, err := io.WriteString(w, b.String())
	return err
}
