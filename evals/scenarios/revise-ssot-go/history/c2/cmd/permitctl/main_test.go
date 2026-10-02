package main

import (
	"bytes"
	"strings"
	"testing"
)

func cli(args ...string) (int, string, string) {
	var out, errb bytes.Buffer
	rc := run(args, &out, &errb)
	return rc, out.String(), errb.String()
}

func TestQuoteBandA(t *testing.T) {
	rc, out, _ := cli("quote", "-co2", "87")
	if rc != 0 || out != "Band A (up to 100 g/km): 32.00\nTotal: 32.00\n" {
		t.Errorf("rc %d, out %q", rc, out)
	}
}

func TestRenewalsNoneDue(t *testing.T) {
	rc, out, _ := cli("renewals", "-month", "2027-06", "testdata/permits.csv")
	if rc != 0 || out != "No renewals due in 2027-06.\n" {
		t.Errorf("rc %d, out %q", rc, out)
	}
}

func TestUsage(t *testing.T) {
	for _, args := range [][]string{
		{},
		{"refund"},
		{"quote"},
		{"quote", "-co2", "-5"},
		{"quote", "-co2", "lots"},
		{"quote", "-co2", "120", "-fuel", "lpg"},
		{"renewals", "testdata/permits.csv"},
		{"renewals", "-month", "April", "testdata/permits.csv"},
	} {
		if rc, _, _ := cli(args...); rc != 2 {
			t.Errorf("%q: exit %d, want 2", args, rc)
		}
	}
}

func TestExportErrors(t *testing.T) {
	for _, args := range [][]string{
		{"renewals", "-month", "2027-04", "testdata/missing.csv"},
	} {
		rc, _, errb := cli(args...)
		if rc != 1 || !strings.HasPrefix(errb, "permitctl: ") {
			t.Errorf("%q: exit %d, stderr %q", args, rc, errb)
		}
	}
}
