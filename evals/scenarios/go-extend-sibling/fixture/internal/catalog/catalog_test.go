package catalog

import (
	"errors"
	"strings"
	"testing"
	"time"
)

const sample = "# exported 2026-01-07T04:00:00Z\n" +
	"s-1001\tdb-1\tpgdump\t2026-01-05T02:00:04Z\t1834201923\tok\t-\n" +
	"\n" +
	"s-1002\tdb-1\tpgdump\t2026-01-06T02:00:03+02:00\t1834988120\tok\tpinned,pre-upgrade\n" +
	"s-1003\tweb-1\tetc\t2026-01-06T03:10:00Z\t1203332\tpartial\t-\r\n"

func TestParseSample(t *testing.T) {
	snaps, err := Parse(strings.NewReader(sample), "sample.tsv")
	if err != nil {
		t.Fatal(err)
	}
	if len(snaps) != 3 {
		t.Fatalf("got %d snapshots, want 3", len(snaps))
	}
	s := snaps[1]
	if s.ID != "s-1002" || s.Series() != "db-1/pgdump" || s.Bytes != 1834988120 || s.State != OK || s.Line != 4 {
		t.Errorf("unexpected snapshot %+v", s)
	}
	if want := time.Date(2026, 1, 6, 0, 0, 3, 0, time.UTC); !s.Created.Equal(want) || s.Created.Location() != time.UTC {
		t.Errorf("created %v, want %v in UTC", s.Created, want)
	}
	if !s.HasTag("pinned") || s.HasTag("pin") || len(s.Tags) != 2 {
		t.Errorf("tags %v", s.Tags)
	}
	if snaps[2].State != Partial || snaps[2].Tags != nil {
		t.Errorf("third snapshot %+v", snaps[2])
	}
}

func TestFormatTimeIsUTC(t *testing.T) {
	when := time.Date(2026, 1, 6, 2, 0, 3, 0, time.FixedZone("CEST", 2*3600))
	if got := FormatTime(when); got != "2026-01-06T00:00:03Z" {
		t.Errorf("FormatTime = %q", got)
	}
}

func TestParseErrorsNameTheLine(t *testing.T) {
	cases := map[string]string{
		"s-1\tdb-1\tpgdump\t2026-01-05\t10\tok\t-\n":                                                           "line 1: bad created time",
		"# c\ns-1\tdb-1\tpgdump\t2026-01-05T02:00:00Z\t1.5\tok\t-\n":                                           "line 2: bad byte count",
		"s-1\tdb-1\tpgdump\t2026-01-05T02:00:00Z\t10\tdone\t-\n":                                               "line 1: bad state",
		"s-1\tdb-1\tpgdump\t2026-01-05T02:00:00Z\t10\tok\n":                                                    "line 1: want 7 tab-separated fields, got 6",
		"s-1\tdb 1\tpgdump\t2026-01-05T02:00:00Z\t10\tok\t-\n":                                                 "line 1: bad host",
		"s-1\tdb-1\tpgdump\t2026-01-05T02:00:00Z\t10\tok\tpinned,\n":                                           "line 1: bad tag list",
		"s-1\tdb-1\tpgdump\t2026-01-05T02:00:00Z\t10\tok\t-\n\ns-1\tdb-1\tx\t2026-01-05T02:00:00Z\t1\tok\t-\n": "line 3: duplicate id s-1 (first on line 1)",
	}
	for input, want := range cases {
		_, err := Parse(strings.NewReader(input), "c.tsv")
		var ce *Error
		if !errors.As(err, &ce) {
			t.Errorf("%q: error %v, want a catalog error", input, err)
			continue
		}
		if !strings.Contains(err.Error(), want) || !strings.HasPrefix(err.Error(), "c.tsv line ") {
			t.Errorf("%q: error %q, want it to contain %q", input, err, want)
		}
	}
}

func TestLoadStdinAndMissingFile(t *testing.T) {
	snaps, err := Load("-", strings.NewReader(sample))
	if err != nil || len(snaps) != 3 {
		t.Fatalf("stdin: %d snapshots, %v", len(snaps), err)
	}
	if _, err := Load("testdata-does-not-exist.tsv", nil); err == nil {
		t.Error("missing file: no error")
	}
}

func TestFilter(t *testing.T) {
	snaps, _ := Parse(strings.NewReader(sample), "sample.tsv")
	if got := len(Filter(snaps, "db-1", "")); got != 2 {
		t.Errorf("host filter kept %d", got)
	}
	if got := len(Filter(snaps, "", "etc")); got != 1 {
		t.Errorf("set filter kept %d", got)
	}
	if got := len(Filter(snaps, "db-1", "etc")); got != 0 {
		t.Errorf("host and set filter kept %d", got)
	}
}
