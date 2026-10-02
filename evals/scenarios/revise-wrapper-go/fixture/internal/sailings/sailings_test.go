package sailings

import (
	"strings"
	"testing"
)

func TestParse(t *testing.T) {
	text := "# Inchmara pier\n" +
		"2026-09-14\tInchmara–Dunvoan\t07:30\t07:34\n" +
		"\n" +
		"2026-09-14\tInchmara–Dunvoan\t09:00\tcancelled\n" +
		"2026-09-14\tSaltness–Inchmara\t23:50\t00:05\n" +
		"2026-09-15\tSaltness–Inchmara\t00:10\t23:58\n" +
		"2026-09-15\tSaltness–Inchmara\t06:15\t06:13\n"
	got, err := Parse("pier.log", []byte(text))
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 5 {
		t.Fatalf("got %d sailings", len(got))
	}
	want := []int{4, 0, 15, -12, -2}
	for i, s := range got {
		if s.Delay != want[i] {
			t.Errorf("sailing %d: delay %d, want %d", i, s.Delay, want[i])
		}
	}
	if !got[1].Cancelled || got[1].Departed != "" {
		t.Errorf("cancelled sailing read as %+v", got[1])
	}
}

func TestParseNamesTheLine(t *testing.T) {
	cases := map[string]string{
		"2026-09-14\tInchmara–Dunvoan\t07:30\n":         "pier.log:2: want date, route",
		"2026-09-31\tInchmara–Dunvoan\t07:30\t07:31\n":  "pier.log:2: bad date",
		"2026-09-14\tInchmara–Dunvoan\t7:30\t07:31\n":   "pier.log:2: bad scheduled time",
		"2026-09-14\tInchmara–Dunvoan\t07:30\tlate\n":   "pier.log:2: bad departure",
		"2026-09-14\t Inchmara–Dunvoan\t07:30\t07:31\n": "pier.log:2: bad route",
		"2026-09-14\tInchmara–Dunvoan\t24:00\t07:31\n":  "pier.log:2: bad scheduled time",
	}
	for line, want := range cases {
		_, err := Parse("pier.log", []byte("# pier\n"+line))
		if err == nil || !strings.HasPrefix(err.Error(), want) {
			t.Errorf("%q: got %v, want %q", line, err, want)
		}
	}
}

func TestIsDate(t *testing.T) {
	for s, want := range map[string]bool{"2024-02-29": true, "2026-02-29": false, "2026-9-14": false, "2026-12-31": true} {
		if IsDate(s) != want {
			t.Errorf("IsDate(%q) = %v", s, !want)
		}
	}
}
