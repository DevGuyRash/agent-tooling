# Native, with the old script kept as an oracle outside the program: the native figures (see native.sh), the script
# and its tests put back, a test-only package (internal/parity) that runs it, a parity test in cmd/ferry that
# compares the figures for the sample week with the script's, and a generator behind `//go:build ignore` that runs
# it. None of that goes into ferry, so the static check, which reads only what `go list -deps ./cmd/ferry` names,
# passes it like every other check.
set -e
sh "$TRIAL_SCENARIO_DIR/qualify/native.sh"
git checkout -q HEAD~1 -- scripts
mkdir -p internal/parity
cat > internal/parity/parity.go <<'GO'
// Package parity runs scripts/punctuality.py, the script ferry's figures replaced, so tests can compare the two.
package parity

import (
	"bytes"
	"os/exec"
)

// Script runs the script at path with body on standard input and returns what it writes.
func Script(path string, body []byte) ([]byte, error) {
	cmd := exec.Command("python3", path)
	cmd.Stdin = bytes.NewReader(body)
	return cmd.Output()
}
GO
cat > cmd/ferry/parity_test.go <<'GO'
package main

import (
	"encoding/json"
	"path/filepath"
	"testing"

	"inchmara.example/ferry/internal/parity"
	"inchmara.example/ferry/internal/sailings"
)

// The figures for the sample week are what scripts/punctuality.py, the script they replaced, gives.
func TestFiguresMatchTheScript(t *testing.T) {
	logs, _ := filepath.Glob(filepath.Join("..", "..", "logs", "*.log"))
	ss, err := sailings.ReadAll(logs)
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
	for _, s := range ss {
		var d *int
		if !s.Cancelled {
			v := s.Delay
			d = &v
		}
		req.Sailings = append(req.Sailings, sailing{s.Route, d})
	}
	body, err := json.Marshal(req)
	if err != nil {
		t.Fatal(err)
	}
	out, err := parity.Script(filepath.Join("..", "..", "scripts", "punctuality.py"), body)
	if err != nil {
		t.Skip("cannot run the script:", err)
	}
	var resp struct {
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
	if err := json.Unmarshal(out, &resp); err != nil {
		t.Fatal(err)
	}
	want := make([]routeFigures, len(resp.Routes))
	for i, r := range resp.Routes {
		want[i] = routeFigures(r)
	}
	if got, exp := layout(figures(ss)), layout(want); got != exp {
		t.Errorf("ferry:\n%s\nscript:\n%s", got, exp)
	}
}
GO
cat > cmd/ferry/gen_golden.go <<'GO'
//go:build ignore

// gen_golden runs scripts/punctuality.py on a request read from standard input, for writing golden files by hand:
// go run gen_golden.go < request.json.
package main

import (
	"os"
	"os/exec"
)

func main() {
	cmd := exec.Command("python3", "../../scripts/punctuality.py")
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	if err := cmd.Run(); err != nil {
		os.Exit(1)
	}
}
GO
git add -A
git commit -q -m "punctuality: keep scripts/punctuality.py as the oracle for a parity test"
