package issue

import (
	"fmt"
	"runtime"
	"testing"

	"northgate.example/gatepass/internal/sales"
)

// The list must not depend on how many CPUs derive the codes.
func TestPassesSameOnAnyCPUCount(t *testing.T) {
	var rows []sales.Row
	for i := 0; i < 40; i++ {
		rows = append(rows, sales.Row{Line: i + 2, Order: "O", PassID: fmt.Sprintf("P-%06d", i%29), Zone: "NORTH"})
	}
	prev := runtime.GOMAXPROCS(1)
	defer runtime.GOMAXPROCS(prev)
	one, _ := Passes(rows, secret, "EVT-1")
	runtime.GOMAXPROCS(8)
	many, _ := Passes(rows, secret, "EVT-1")
	if len(one) != len(many) {
		t.Fatalf("%d passes on one CPU, %d on eight", len(one), len(many))
	}
	for i := range one {
		if one[i] != many[i] {
			t.Errorf("pass %d: %+v on one CPU, %+v on eight", i, one[i], many[i])
		}
	}
}
