package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestSkipsMalformedLines(t *testing.T) {
	s := newSummary("")
	s.add(`1.2.3.4 - - [x +0000] "GET /a HTTP/1.1" 200 10 "-" "-"`)
	s.add(`1.2.3.4 - - [x +0000] "-" 400 0 "-" "-"`)
	s.add(`1.2.3.4 - - [x +0000] "GET /a HTTP/1.1" 999 10 "-" "-"`)
	s.add(`1.2.3.4 - - [x +0000] "GET /a HTTP/1.1"`)
	if s.requests != 1 {
		t.Fatalf("requests = %d, want 1", s.requests)
	}
}

func TestTiesInByteOrder(t *testing.T) {
	got := topN(map[string]int{"/b": 2, "/A": 2, "/a": 2, "/z": 3}, 3)
	want := []string{"/z", "/A", "/a"}
	for i, e := range got {
		if e.key != want[i] {
			t.Fatalf("topN = %v, want keys %v", got, want)
		}
	}
}

func TestUsageErrors(t *testing.T) {
	for _, args := range [][]string{{"-n", "x"}, {"-s", "5xx"}, {"-q"}} {
		var out, errb bytes.Buffer
		if code := run(args, strings.NewReader(""), &out, &errb); code != 2 || out.Len() != 0 {
			t.Errorf("run(%v) = %d with output %q, want 2 and none", args, code, out.String())
		}
	}
}
