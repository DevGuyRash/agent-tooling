package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const logText = "# Inchmara pier, week 38\n" +
	"2026-09-14\tInchmara–Dunvoan\t07:30\t07:34\n" +
	"2026-09-14\tSaltness–Inchmara\t07:30\t07:29\n" +
	"2026-09-14\tInchmara–Dunvoan\t09:00\tcancelled\n" +
	"2026-09-14\tKilbride–Eilean Rùm\t08:15\t08:41\n" +
	"2026-09-14\tSaltness–Inchmara\t23:50\t00:05\n" +
	"2026-09-15\tInchmara–Dunvoan\t07:30\t07:30\n" +
	"2026-09-15\tSaltness–Inchmara\t07:30\t07:38\n" +
	"2026-09-15\tKilbride–Eilean Rùm\t08:15\t08:17\n" +
	"2026-09-15\tInchmara–Dunvoan\t09:00\t09:03\n"

// ferry runs the command in-process; "week.log" in args names a log with logText in a temporary directory.
func ferry(t *testing.T, args ...string) (code int, stdout, stderr string) {
	t.Helper()
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "week.log"), []byte(logText), 0o644); err != nil {
		t.Fatal(err)
	}
	for i, a := range args {
		if a == "week.log" {
			args[i] = filepath.Join(dir, a)
		}
	}
	var out, errb bytes.Buffer
	code = run(args, &out, &errb)
	return code, strings.ReplaceAll(out.String(), dir+string(filepath.Separator), ""), errb.String()
}

func TestCheck(t *testing.T) {
	code, out, _ := ferry(t, "check", "week.log")
	if code != 0 || out != "week.log: 9 sailings, 3 routes, 2 days, 1 cancelled\n" {
		t.Errorf("exit %d, output %q", code, out)
	}
}

func TestCheckNamesTheLineAndGoesOn(t *testing.T) {
	bad := filepath.Join(t.TempDir(), "bad.log")
	if err := os.WriteFile(bad, []byte("# pier\n2026-09-14\tInchmara–Dunvoan\t07:30\tlate\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	code, out, errs := ferry(t, "check", bad, "week.log")
	if code != 1 || !strings.Contains(errs, "bad.log:2: bad departure") || out != "week.log: 9 sailings, 3 routes, 2 days, 1 cancelled\n" {
		t.Errorf("exit %d, output %q, errors %q", code, out, errs)
	}
}

func TestDay(t *testing.T) {
	code, out, _ := ferry(t, "day", "2026-09-14", "week.log")
	want := "" +
		"sched  route                departed   delay\n" +
		"07:30  Inchmara–Dunvoan     07:34      +4\n" +
		"07:30  Saltness–Inchmara    07:29      -1\n" +
		"08:15  Kilbride–Eilean Rùm  08:41      +26\n" +
		"09:00  Inchmara–Dunvoan     cancelled  -\n" +
		"23:50  Saltness–Inchmara    00:05      +15\n"
	if code != 0 || out != want {
		t.Errorf("exit %d, output\n%s\nwant\n%s", code, out, want)
	}
}

func TestPunctuality(t *testing.T) {
	t.Setenv("FERRY_SCRIPTS", filepath.Join("..", "..", "scripts"))
	code, out, errs := ferry(t, "punctuality", "week.log")
	want := "" +
		"route                sailings  cancelled  on time  median  worst  by 5 minutes\n" +
		"Saltness–Inchmara           3          0        1       8     15  -5:1 5:1 15:1\n" +
		"Kilbride–Eilean Rùm         2          0        1      14     26  0:1 25:1\n" +
		"Inchmara–Dunvoan            4          1        3       3      4  0:3\n" +
		"\n" +
		"9 sailings, 1 cancelled, 5 of 8 on time\n"
	if code != 0 || out != want {
		t.Errorf("exit %d, errors %q, output\n%s\nwant\n%s", code, errs, out, want)
	}
}

func TestPunctualityDates(t *testing.T) {
	t.Setenv("FERRY_SCRIPTS", filepath.Join("..", "..", "scripts"))
	code, out, _ := ferry(t, "punctuality", "--from", "2026-09-15", "--to", "2026-09-15", "week.log")
	if code != 0 || !strings.HasSuffix(out, "\n4 sailings, 0 cancelled, 3 of 4 on time\n") {
		t.Errorf("exit %d, output\n%s", code, out)
	}
	code, out, _ = ferry(t, "punctuality", "--from", "2026-10-01", "week.log")
	if code != 0 || out != "no sailings\n" {
		t.Errorf("exit %d, output %q", code, out)
	}
}

func TestUsageErrors(t *testing.T) {
	for _, args := range [][]string{{}, {"punctuality"}, {"punctuality", "--from", "15/09/2026", "week.log"},
		{"punctuality", "--from", "2026-09-16", "--to", "2026-09-15", "week.log"}, {"day", "week.log"}, {"sail"}} {
		if code, _, _ := ferry(t, args...); code != 2 {
			t.Errorf("%q: exit %d, want 2", args, code)
		}
	}
}
