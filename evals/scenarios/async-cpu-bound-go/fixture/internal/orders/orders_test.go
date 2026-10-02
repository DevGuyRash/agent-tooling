package orders

import (
	"strings"
	"testing"
)

const export = `order_id,placed_at,sku,qty
K-2,2026-09-30T21:00:00Z,MUG-TI,2
K-1,2026-09-30T20:00:00Z,TENT-2P,1
K-2,2026-09-30T21:00:00Z,HEADLAMP,1
`

func TestLoadGroupsRows(t *testing.T) {
	list, err := Load(strings.NewReader(export))
	if err != nil {
		t.Fatal(err)
	}
	if len(list) != 2 || list[0].ID != "K-2" || list[1].ID != "K-1" {
		t.Fatalf("orders %v", list)
	}
	if len(list[0].Lines) != 2 || list[0].Lines[1] != (Line{"HEADLAMP", 1}) || list[0].Units() != 3 {
		t.Errorf("K-2 lines %v", list[0].Lines)
	}
}

func TestLoadRejects(t *testing.T) {
	for _, body := range []string{
		"K-1,2026-09-30T20:00:00Z,TENT-2P,0\n",
		"K-1,yesterday,TENT-2P,1\n",
		"K-1,2026-09-30T20:00:00Z,TENT-2P,1\nK-1,2026-09-30T20:00:01Z,MUG-TI,1\n",
	} {
		if _, err := Load(strings.NewReader("order_id,placed_at,sku,qty\n" + body)); err == nil {
			t.Errorf("accepted %q", body)
		}
	}
}
