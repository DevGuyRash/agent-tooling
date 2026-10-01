package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const catalogText = "# id\thost\tset\tcreated\tbytes\tstate\ttags\n" +
	"s-2001\tdb-1\tpgdump\t2026-01-05T02:00:04Z\t1834201923\tok\t-\n" +
	"s-2002\tdb-1\tpgdump\t2026-01-06T02:00:03Z\t1834988120\tok\tpinned\n" +
	"s-2003\tweb-1\tetc\t2026-01-06T03:10:00Z\t1203332\tpartial\t-\n" +
	"s-2004\tweb-1\tetc\t2026-01-05T03:10:00Z\t1201100\tok\t-\n"

// bakctl runs the command in-process on a catalog file in a temporary directory.
func bakctl(t *testing.T, stdin string, args ...string) (code int, stdout, stderr string) {
	t.Helper()
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "catalog.tsv"), []byte(catalogText), 0o644); err != nil {
		t.Fatal(err)
	}
	for i, a := range args {
		if a == "catalog.tsv" {
			args[i] = filepath.Join(dir, a)
		}
	}
	var out, errb bytes.Buffer
	code = run(args, strings.NewReader(stdin), &out, &errb)
	return code, out.String(), errb.String()
}

func TestListFilters(t *testing.T) {
	code, out, _ := bakctl(t, "", "list", "--host", "web-1", "catalog.tsv")
	if code != 0 {
		t.Fatalf("exit %d", code)
	}
	want := "" +
		"ID      SERIES     CREATED               SIZE     STATE    TAGS\n" +
		"s-2004  web-1/etc  2026-01-05T03:10:00Z  1.1 MiB  ok       -\n" +
		"s-2003  web-1/etc  2026-01-06T03:10:00Z  1.1 MiB  partial  -\n"
	if out != want {
		t.Errorf("output:\n%s\nwant:\n%s", out, want)
	}
	code, out, _ = bakctl(t, "", "list", "--state=ok", "--set", "pgdump", "catalog.tsv")
	if code != 0 || strings.Count(out, "\n") != 3 || strings.Contains(out, "web-1") {
		t.Errorf("state and set filter: exit %d\n%s", code, out)
	}
}

func TestListReadsStdin(t *testing.T) {
	code, out, _ := bakctl(t, catalogText, "list", "-")
	if code != 0 || strings.Count(out, "\n") != 5 {
		t.Errorf("exit %d\n%s", code, out)
	}
}

func TestUsageBySeries(t *testing.T) {
	code, out, _ := bakctl(t, "", "usage", "--by", "series", "catalog.tsv")
	want := "" +
		"SERIES       SNAPSHOTS     SIZE\n" +
		"db-1/pgdump          2  3.4 GiB\n" +
		"web-1/etc            2  2.3 MiB\n" +
		"total                4  3.4 GiB\n"
	if code != 0 || out != want {
		t.Errorf("exit %d, output:\n%s\nwant:\n%s", code, out, want)
	}
}

func TestCheck(t *testing.T) {
	code, out, _ := bakctl(t, "", "check", "catalog.tsv")
	if code != 0 || out != "ok: 4 snapshots in 2 series: 3 ok, 1 partial, 0 failed\n" {
		t.Errorf("exit %d, output %q", code, out)
	}
}

func TestExitStatuses(t *testing.T) {
	cases := []struct {
		args   []string
		stdin  string
		code   int
		stderr string
	}{
		{nil, "", 2, "usage: bakctl"},
		{[]string{"prnue", "catalog.tsv"}, "", 2, `unknown command "prnue"`},
		{[]string{"list"}, "", 2, "want one CATALOG argument, got 0"},
		{[]string{"list", "catalog.tsv", "catalog.tsv"}, "", 2, "want one CATALOG argument, got 2"},
		{[]string{"list", "--bogus", "catalog.tsv"}, "", 2, "flag provided but not defined"},
		{[]string{"list", "--state", "done", "catalog.tsv"}, "", 2, "--state wants ok, partial, or failed"},
		{[]string{"usage", "--by", "set", "catalog.tsv"}, "", 2, "--by wants host or series"},
		{[]string{"list", "no-such-catalog.tsv"}, "", 1, "bakctl: open no-such-catalog.tsv"},
		{[]string{"check", "-"}, "s-1\tdb-1\tpgdump\tyesterday\t1\tok\t-\n", 1, "bakctl: stdin line 1: bad created time"},
	}
	for _, c := range cases {
		code, out, errText := bakctl(t, c.stdin, c.args...)
		if code != c.code || out != "" || !strings.Contains(errText, c.stderr) {
			t.Errorf("%v: exit %d (want %d), stdout %q, stderr %q (want %q)", c.args, code, c.code, out, errText, c.stderr)
		}
	}
}
