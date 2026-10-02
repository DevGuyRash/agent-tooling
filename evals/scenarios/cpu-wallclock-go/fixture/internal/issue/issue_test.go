package issue

import (
	"bytes"
	"testing"

	"northgate.example/gatepass/internal/passcode"
	"northgate.example/gatepass/internal/sales"
)

var secret = bytes.Repeat([]byte{0x5a}, 16)

func TestPassesReissue(t *testing.T) {
	rows := []sales.Row{
		{Line: 2, Order: "O-1", PassID: "P-000010", Zone: "NORTH"},
		{Line: 3, Order: "O-2", PassID: "P-000011", Zone: "SOUTH"},
		{Line: 4, Order: "O-3", PassID: "P-000010", Zone: "EAST"},
		{Line: 5, Order: "O-4", PassID: "P-000012", Zone: "WEST"},
		{Line: 6, Order: "O-5", PassID: "P-000010", Zone: "EAST"},
	}
	passes, s := Passes(rows, secret, "EVT-1")
	want := []Pass{
		{"P-000010", "EAST", 2, passcode.Code(secret, "EVT-1", "P-000010", 2)},
		{"P-000011", "SOUTH", 0, passcode.Code(secret, "EVT-1", "P-000011", 0)},
		{"P-000012", "WEST", 0, passcode.Code(secret, "EVT-1", "P-000012", 0)},
	}
	if len(passes) != len(want) {
		t.Fatalf("got %d passes, want %d", len(passes), len(want))
	}
	for i := range want {
		if passes[i] != want[i] {
			t.Errorf("pass %d = %+v, want %+v", i, passes[i], want[i])
		}
	}
	if s != (Summary{Rows: 5, Passes: 3, Reissued: 1}) {
		t.Errorf("summary = %+v", s)
	}
}

func TestWrite(t *testing.T) {
	var buf bytes.Buffer
	if err := Write(&buf, []Pass{{"P-000010", "EAST", 2, "AAAA-BBBB-CCCC-DDDD"}}); err != nil {
		t.Fatal(err)
	}
	if got := buf.String(); got != "pass_id,zone,issue,code\nP-000010,EAST,2,AAAA-BBBB-CCCC-DDDD\n" {
		t.Errorf("Write wrote %q", got)
	}
}
