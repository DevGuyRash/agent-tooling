package main

import (
	"bytes"
	"os"
	"strings"
	"testing"
)

func TestBuildSample(t *testing.T) {
	var out, errs bytes.Buffer
	code := run([]string{"build", "-event", "EVT-2026-0412", "-key", "../../testdata/sample.key",
		"../../testdata/sample-sales.csv"}, &out, &errs)
	if code != 0 {
		t.Fatalf("exit %d: %s", code, errs.String())
	}
	want, err := os.ReadFile("../../testdata/sample-turnstile.csv")
	if err != nil {
		t.Fatal(err)
	}
	if out.String() != string(want) {
		t.Errorf("turnstile file differs from testdata/sample-turnstile.csv:\n%s", out.String())
	}
	if !strings.Contains(errs.String(), "10 passes (1 reissued) from 12 rows") {
		t.Errorf("summary: %q", errs.String())
	}
}

func TestBuildBadRow(t *testing.T) {
	dir := t.TempDir()
	path := dir + "/sales.csv"
	export := "order_id,pass_id,zone,holder\nO-1,P-000001,NORTH,A\nO-2,P-000002,MOON,B\n"
	if err := os.WriteFile(path, []byte(export), 0o600); err != nil {
		t.Fatal(err)
	}
	var out, errs bytes.Buffer
	code := run([]string{"build", "-event", "E", "-key", "../../testdata/sample.key", path}, &out, &errs)
	if code != 1 || out.Len() != 0 || !strings.Contains(errs.String(), "line 3") {
		t.Errorf("exit %d, stdout %q, stderr %q", code, out.String(), errs.String())
	}
}

func TestVerify(t *testing.T) {
	var out, errs bytes.Buffer
	args := []string{"verify", "-event", "EVT-2026-0412", "-key", "../../testdata/sample.key", "P-104233", "0"}
	if code := run(append(args, "m9fj-7xd3-62mq-w9nh"), &out, &errs); code != 0 {
		t.Errorf("verify of a good code: exit %d, %s%s", code, out.String(), errs.String())
	}
	if code := run(append(args, "M9FJ-7XD3-62MQ-W9NJ"), &out, &errs); code != 1 {
		t.Errorf("verify of a bad code: exit %d", code)
	}
}

func TestUsage(t *testing.T) {
	for _, args := range [][]string{
		{}, {"frobnicate"}, {"build"}, {"build", "-event", "E", "-key", "../../testdata/sample.key"},
	} {
		var out, errs bytes.Buffer
		if code := run(args, &out, &errs); code != 2 {
			t.Errorf("%v: exit %d, want 2", args, code)
		}
	}
}
