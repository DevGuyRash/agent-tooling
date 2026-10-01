package report

import (
	"bytes"
	"strings"
	"testing"

	"tidewater.example/bakctl/internal/catalog"
)

const sample = "s-1004\tweb-1\twww\t2026-01-06T03:20:00Z\t88\tfailed\t-\n" +
	"s-1002\tdb-1\tpgdump\t2026-01-06T02:00:03+02:00\t1834988120\tok\tpinned,pre-upgrade\n" +
	"s-1003\tweb-1\tetc\t2026-01-06T03:10:00Z\t1203332\tpartial\t-\n" +
	"s-1001\tdb-1\tpgdump\t2026-01-05T02:00:04Z\t1834201923\tok\t-\n"

func load(t *testing.T) []catalog.Snapshot {
	t.Helper()
	snaps, err := catalog.Parse(strings.NewReader(sample), "sample.tsv")
	if err != nil {
		t.Fatal(err)
	}
	return snaps
}

func TestList(t *testing.T) {
	var b bytes.Buffer
	if err := List(&b, load(t)); err != nil {
		t.Fatal(err)
	}
	want := "" +
		"ID      SERIES       CREATED               SIZE     STATE    TAGS\n" +
		"s-1001  db-1/pgdump  2026-01-05T02:00:04Z  1.7 GiB  ok       -\n" +
		"s-1002  db-1/pgdump  2026-01-06T00:00:03Z  1.7 GiB  ok       pinned,pre-upgrade\n" +
		"s-1003  web-1/etc    2026-01-06T03:10:00Z  1.1 MiB  partial  -\n" +
		"s-1004  web-1/www    2026-01-06T03:20:00Z  88 B     failed   -\n"
	if b.String() != want {
		t.Errorf("List output:\n%s\nwant:\n%s", b.String(), want)
	}
}

func TestSortedBreaksTimeTiesByID(t *testing.T) {
	snaps, err := catalog.Parse(strings.NewReader(
		"b\th\ts\t2026-01-01T00:00:00Z\t1\tok\t-\n"+
			"a\th\ts\t2026-01-01T01:00:00+01:00\t1\tok\t-\n"), "ties.tsv")
	if err != nil {
		t.Fatal(err)
	}
	got := Sorted(snaps)
	if got[0].ID != "a" || got[1].ID != "b" {
		t.Errorf("order %s, %s", got[0].ID, got[1].ID)
	}
}

func TestUsageByHostAndSeries(t *testing.T) {
	var b bytes.Buffer
	if err := Usage(&b, load(t), "host"); err != nil {
		t.Fatal(err)
	}
	want := "" +
		"HOST   SNAPSHOTS     SIZE\n" +
		"db-1           2  3.4 GiB\n" +
		"web-1          2  1.1 MiB\n" +
		"total          4  3.4 GiB\n"
	if b.String() != want {
		t.Errorf("by host:\n%s\nwant:\n%s", b.String(), want)
	}
	b.Reset()
	if err := Usage(&b, load(t), "series"); err != nil {
		t.Fatal(err)
	}
	want = "" +
		"SERIES       SNAPSHOTS     SIZE\n" +
		"db-1/pgdump          2  3.4 GiB\n" +
		"web-1/etc            1  1.1 MiB\n" +
		"web-1/www            1     88 B\n" +
		"total                4  3.4 GiB\n"
	if b.String() != want {
		t.Errorf("by series:\n%s\nwant:\n%s", b.String(), want)
	}
}

func TestSummary(t *testing.T) {
	if got, want := Summary(load(t)), "4 snapshots in 3 series: 2 ok, 1 partial, 1 failed"; got != want {
		t.Errorf("Summary = %q, want %q", got, want)
	}
}
