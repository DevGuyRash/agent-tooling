package sales

import (
	"strings"
	"testing"
)

func TestRead(t *testing.T) {
	export := "holder,zone,pass_id,order_id\n\"Okafor, Chidi\",family,P-000001,O-1\nSam Patel, NORTH ,P-000002,O-2\n"
	rows, err := Read(strings.NewReader(export))
	if err != nil {
		t.Fatal(err)
	}
	want := []Row{
		{Line: 2, Order: "O-1", PassID: "P-000001", Zone: "FAMILY", Holder: "Okafor, Chidi"},
		{Line: 3, Order: "O-2", PassID: "P-000002", Zone: "NORTH", Holder: "Sam Patel"},
	}
	if len(rows) != len(want) {
		t.Fatalf("got %d rows, want %d", len(rows), len(want))
	}
	for i := range want {
		if rows[i] != want[i] {
			t.Errorf("row %d = %+v, want %+v", i, rows[i], want[i])
		}
	}
}

func TestReadHeaderOnly(t *testing.T) {
	rows, err := Read(strings.NewReader("order_id,pass_id,zone,holder\n"))
	if err != nil || len(rows) != 0 {
		t.Fatalf("Read = %v, %v", rows, err)
	}
}

func TestReadErrors(t *testing.T) {
	for export, want := range map[string]string{
		"":                          "empty export",
		"order_id,pass_id,holder\n": "line 1: no zone column",
		"order_id,pass_id,zone,holder\nO-1,P-000001,NORTH,A\nO-2,P-12,NORTH,B\n": "line 3: bad pass_id",
		"order_id,pass_id,zone,holder\nO-1,P-000001,MOON,A\n":                    "line 2: unknown zone",
		"order_id,pass_id,zone,holder\n,P-000001,NORTH,A\n":                      "line 2: no order_id",
	} {
		_, err := Read(strings.NewReader(export))
		if err == nil || !strings.Contains(err.Error(), want) {
			t.Errorf("Read(%q) error = %v, want %q", export, err, want)
		}
	}
}
