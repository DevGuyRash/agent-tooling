package prune

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"

	"tidewater.example/bakctl/internal/catalog"
)

// TestMatchesNightlyRetention runs the nightly job's retention script on the example catalog and checks that
// Plan makes the same decisions for the rules both know (last, daily, weekly, monthly). The script is only an
// oracle here; bakctl itself never runs it.
func TestMatchesNightlyRetention(t *testing.T) {
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 not available")
	}
	root := filepath.Join("..", "..")
	example := filepath.Join(root, "docs", "prune-example.tsv")
	data, err := os.ReadFile(example)
	if err != nil {
		t.Fatal(err)
	}
	snaps, err := catalog.Parse(bytes.NewReader(data), example)
	if err != nil {
		t.Fatal(err)
	}
	for _, p := range []Policy{{Last: 2, Daily: 3, Weekly: 2}, {Daily: 7}, {Last: 1, Weekly: 5, Monthly: 2}} {
		cmd := exec.Command(python, filepath.Join(root, "scripts", "retention.py"), "--json",
			"--last", strconv.Itoa(p.Last), "--daily", strconv.Itoa(p.Daily), "--weekly", strconv.Itoa(p.Weekly), "--monthly", strconv.Itoa(p.Monthly),
			example)
		out, err := cmd.Output()
		if err != nil {
			t.Fatalf("%+v: retention.py: %v", p, err)
		}
		var rows []struct {
			ID    string   `json:"id"`
			State string   `json:"state"`
			Rules []string `json:"rules"`
		}
		if err := json.Unmarshal(out, &rows); err != nil {
			t.Fatal(err)
		}
		want := map[string][]string{}
		for _, r := range rows {
			if r.State == "ok" {
				want[r.ID] = append([]string{}, r.Rules...)
			}
		}
		got := map[string][]string{}
		for _, s := range Plan(snaps, p) {
			for _, d := range s.Decisions {
				if d.Snapshot.State != catalog.OK {
					continue
				}
				rules := []string{}
				for _, r := range d.Reasons {
					if strings.Contains(" last daily weekly monthly ", " "+r+" ") {
						rules = append(rules, r)
					}
				}
				got[d.Snapshot.ID] = rules
			}
		}
		if !reflect.DeepEqual(got, want) {
			t.Errorf("%+v:\nPlan:         %v\nretention.py: %v", p, got, want)
		}
	}
}
