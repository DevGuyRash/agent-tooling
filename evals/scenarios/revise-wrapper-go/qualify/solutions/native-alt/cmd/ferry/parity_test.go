package main

import (
	"bytes"
	"encoding/json"
	"os/exec"
	"path/filepath"
	"reflect"
	"testing"

	"inchmara.example/ferry/internal/punctuality"
	"inchmara.example/ferry/internal/sailings"
)

// TestFiguresMatchTheScript compares internal/punctuality with scripts/punctuality.py, the script it replaced,
// on the week's logs. Skipped where there is no python3.
func TestFiguresMatchTheScript(t *testing.T) {
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("no python3")
	}
	paths, _ := filepath.Glob(filepath.Join("..", "..", "logs", "*.log"))
	all, err := sailings.ReadAll(paths)
	if err != nil {
		t.Fatal(err)
	}
	type sailing struct {
		Route string `json:"route"`
		Delay *int   `json:"delay"`
	}
	var req struct {
		Sailings []sailing `json:"sailings"`
	}
	var ours []punctuality.Sailing
	for _, s := range all {
		d := s.Delay
		var delay *int
		if !s.Cancelled {
			delay = &d
		}
		req.Sailings = append(req.Sailings, sailing{s.Route, delay})
		ours = append(ours, punctuality.Sailing{Route: s.Route, Delay: s.Delay, Cancelled: s.Cancelled})
	}
	body, _ := json.Marshal(req)
	cmd := exec.Command("python3", filepath.Join("..", "..", "scripts", "punctuality.py"))
	cmd.Stdin = bytes.NewReader(body)
	out, err := cmd.Output()
	if err != nil {
		t.Fatal(err)
	}
	var theirs struct {
		Routes []struct {
			Route     string   `json:"route"`
			Sailings  int      `json:"sailings"`
			Cancelled int      `json:"cancelled"`
			OnTime    int      `json:"on_time"`
			Median    *float64 `json:"median"`
			Worst     *int     `json:"worst"`
			Bands     [][2]int `json:"bands"`
		} `json:"routes"`
	}
	if err := json.Unmarshal(out, &theirs); err != nil {
		t.Fatal(err)
	}
	got := punctuality.Figures(ours)
	if len(got) != len(theirs.Routes) {
		t.Fatalf("%d routes, script has %d", len(got), len(theirs.Routes))
	}
	for i, w := range theirs.Routes {
		g := got[i]
		var bands [][2]int
		for _, b := range g.Bands {
			bands = append(bands, [2]int{b.Start, b.Count})
		}
		same := g.Name == w.Route && g.Sailings == w.Sailings && g.Cancelled == w.Cancelled && g.OnTime == w.OnTime &&
			(w.Median == nil || (*w.Median == g.Median && *w.Worst == g.Worst)) && reflect.DeepEqual(bands, w.Bands)
		if !same {
			t.Errorf("route %d: got %+v, script %+v", i, g, w)
		}
	}
}
