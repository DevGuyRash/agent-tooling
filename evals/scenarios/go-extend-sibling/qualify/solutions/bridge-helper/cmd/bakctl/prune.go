package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"

	"tidewater.example/bakctl/internal/catalog"
	"tidewater.example/bakctl/internal/humanize"
)

// The last/daily/weekly/monthly rules are the nightly job's, so they come from scripts/retention.py; the rest
// of the policy is computed here.

func retentionScript() string {
	_, file, _, _ := runtime.Caller(0)
	return filepath.Join(filepath.Dir(file), "..", "..", "scripts", "retention.py")
}

var withinPattern = regexp.MustCompile(`^(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?$`)

func runPrune(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := newFlags("prune", stderr)
	rules := []string{"last", "hourly", "daily", "weekly", "monthly", "yearly"}
	raw := map[string]*string{}
	for _, r := range rules {
		raw[r] = fs.String("keep-"+r, "0", "count for the "+r+" rule")
	}
	withinText := fs.String("keep-within", "", "duration")
	host := fs.String("host", "", "host")
	set := fs.String("set", "", "set")
	ids := fs.Bool("ids", false, "ids only")
	path, ok := parse(fs, args, stderr)
	if !ok {
		return 2
	}
	count := map[string]int{}
	any := false
	for _, r := range rules {
		s := *raw[r]
		if s == "" || strings.Trim(s, "0123456789") != "" {
			fmt.Fprintf(stderr, "bakctl prune: --keep-%s wants a whole number, got %q\n", r, s)
			return 2
		}
		n, err := strconv.Atoi(s)
		if err != nil {
			fmt.Fprintf(stderr, "bakctl prune: --keep-%s wants a whole number, got %q\n", r, s)
			return 2
		}
		count[r] = n
		any = any || n > 0
	}
	var within time.Duration
	if *withinText != "" {
		m := withinPattern.FindStringSubmatch(*withinText)
		if m == nil {
			fmt.Fprintf(stderr, "bakctl prune: bad --keep-within %q\n", *withinText)
			return 2
		}
		for i, unit := range []time.Duration{7 * 24 * time.Hour, 24 * time.Hour, time.Hour} {
			if m[i+1] != "" {
				n, _ := strconv.Atoi(m[i+1])
				within += time.Duration(n) * unit
			}
		}
	}
	if !any && within == 0 {
		fmt.Fprintln(stderr, "bakctl prune: refusing to plan without a keep rule")
		return 2
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
	snaps, err := catalog.Parse(bytes.NewReader(data), name)
	if err != nil {
		fmt.Fprintf(stderr, "bakctl: %v\n", err)
		return 1
	}
	snaps = catalog.Filter(snaps, *host, *set)

	// Rules from the nightly script, by snapshot id.
	scripted := map[string][]string{}
	if count["last"]+count["daily"]+count["weekly"]+count["monthly"] > 0 {
		cmd := exec.Command("python3", retentionScript(), "--json",
			"--last", strconv.Itoa(count["last"]), "--daily", strconv.Itoa(count["daily"]),
			"--weekly", strconv.Itoa(count["weekly"]), "--monthly", strconv.Itoa(count["monthly"]), "-")
		cmd.Stdin = bytes.NewReader(data)
		cmd.Stderr = stderr
		out, err := cmd.Output()
		if err != nil {
			fmt.Fprintf(stderr, "bakctl prune: retention.py: %v\n", err)
			return 1
		}
		var rows []struct {
			ID    string   `json:"id"`
			Rules []string `json:"rules"`
		}
		if err := json.Unmarshal(out, &rows); err != nil {
			fmt.Fprintf(stderr, "bakctl prune: retention.py output: %v\n", err)
			return 1
		}
		for _, r := range rows {
			scripted[r.ID] = r.Rules
		}
	}

	series := map[string][]catalog.Snapshot{}
	var keys []string
	for _, s := range snaps {
		k := s.Host + "\x00" + s.Set
		if _, seen := series[k]; !seen {
			keys = append(keys, k)
		}
		series[k] = append(series[k], s)
	}
	sort.Strings(keys)
	var b, idList strings.Builder
	keepAll, dropAll := 0, 0
	var freed int64
	for i, k := range keys {
		members := series[k]
		sort.Slice(members, func(a, c int) bool {
			if !members[a].Created.Equal(members[c].Created) {
				return members[a].Created.After(members[c].Created)
			}
			return members[a].ID < members[c].ID
		})
		var newest *catalog.Snapshot
		for j := range members {
			if members[j].State == catalog.OK {
				newest = &members[j]
				break
			}
		}
		extra := map[string]map[string]bool{}
		mark := func(id, r string) {
			if extra[id] == nil {
				extra[id] = map[string]bool{}
			}
			extra[id][r] = true
		}
		for _, per := range []struct {
			name string
			key  func(time.Time) string
		}{{"hourly", func(t time.Time) string { return t.Format("2006-01-02T15") }},
			{"yearly", func(t time.Time) string { return t.Format("2006") }}} {
			want, prev := count[per.name], ""
			first := true
			for _, s := range members {
				if s.State != catalog.OK || want == 0 {
					continue
				}
				key := per.key(s.Created)
				if first || key != prev {
					mark(s.ID, per.name)
					want--
				}
				prev, first = key, false
			}
		}
		lines := []string{}
		keep := 0
		for _, s := range members {
			var reasons []string
			if s.HasTag("pinned") {
				reasons = append(reasons, "pinned")
			}
			if s.State == catalog.Partial && (newest == nil || s.Created.After(newest.Created)) {
				reasons = append(reasons, "in-progress")
			}
			have := map[string]bool{}
			for _, r := range scripted[s.ID] {
				have[r] = true
			}
			for r := range extra[s.ID] {
				have[r] = true
			}
			if s.State == catalog.OK && within > 0 && !s.Created.Before(newest.Created.Add(-within)) {
				have["within"] = true
			}
			for _, r := range []string{"last", "within", "hourly", "daily", "weekly", "monthly", "yearly"} {
				if have[r] {
					reasons = append(reasons, r)
				}
			}
			action := "keep"
			if len(reasons) == 0 {
				action = "drop"
				reasons = []string{"expired"}
				if s.State != catalog.OK {
					reasons = []string{string(s.State)}
				}
				freed += s.Bytes
				idList.WriteString(s.ID + "\n")
			} else {
				keep++
			}
			lines = append(lines, fmt.Sprintf("  %s  %s  %s  %s", action, s.ID, catalog.FormatTime(s.Created), strings.Join(reasons, ",")))
		}
		if i > 0 {
			b.WriteString("\n")
		}
		hs := strings.SplitN(k, "\x00", 2)
		fmt.Fprintf(&b, "%s/%s: keep %d, drop %d\n%s\n", hs[0], hs[1], keep, len(members)-keep, strings.Join(lines, "\n"))
		keepAll += keep
		dropAll += len(members) - keep
	}
	if *ids {
		io.WriteString(stdout, idList.String())
		return 0
	}
	if len(keys) > 0 {
		b.WriteString("\n")
	}
	fmt.Fprintf(&b, "total: keep %d, drop %d, frees %s\n", keepAll, dropAll, humanize.Bytes(freed))
	io.WriteString(stdout, b.String())
	return 0
}
