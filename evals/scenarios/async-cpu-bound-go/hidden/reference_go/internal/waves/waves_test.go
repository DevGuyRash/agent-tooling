package waves

import (
	"strings"
	"testing"

	"kestrel.example/pickctl/internal/orders"
	"kestrel.example/pickctl/internal/stock"
)

func load(t *testing.T, ordersCSV, stockCSV string) ([]orders.Order, map[string]stock.Item) {
	t.Helper()
	list, err := orders.Load(strings.NewReader("order_id,placed_at,sku,qty\n" + ordersCSV))
	if err != nil {
		t.Fatal(err)
	}
	items, err := stock.Load(strings.NewReader("sku,bin,on_hand\n" + stockCSV))
	if err != nil {
		t.Fatal(err)
	}
	idx, err := stock.Index(items)
	if err != nil {
		t.Fatal(err)
	}
	return list, idx
}

func TestSameSecondByID(t *testing.T) {
	list, idx := load(t, "K-9,2026-09-30T20:00:00Z,STOVE,1\nK-1,2026-09-30T20:00:00Z,STOVE,1\n", "STOVE,A01-01-1,1\n")
	plan := Make(list, idx)
	if len(plan.Waves) != 1 || plan.Waves[0].Picks[0].Order != "K-1" || plan.Short[0].Order != "K-9" {
		t.Fatalf("plan %+v", plan)
	}
}

func TestCartLimits(t *testing.T) {
	var b strings.Builder
	for _, o := range []string{"K-1,2026-09-30T20:00:00Z,GAS,30", "K-2,2026-09-30T20:01:00Z,GAS,30",
		"K-3,2026-09-30T20:02:00Z,GAS,1", "K-4,2026-09-30T20:03:00Z,GAS,70", "K-5,2026-09-30T20:04:00Z,GAS,1"} {
		b.WriteString(o + "\n")
	}
	list, idx := load(t, b.String(), "GAS,A01-01-1,500\n")
	plan := Make(list, idx)
	var got []int
	for _, w := range plan.Waves {
		got = append(got, w.Units)
	}
	if len(got) != 4 || got[0] != 60 || got[1] != 1 || got[2] != 70 || got[3] != 1 {
		t.Fatalf("cart units %v", got)
	}
}

func TestWalkOrderWithinCart(t *testing.T) {
	list, idx := load(t, "K-1,2026-09-30T20:00:00Z,B,1\nK-1,2026-09-30T20:00:00Z,A,1\nK-2,2026-09-30T20:00:01Z,A,1\n",
		"A,A02-09-1,5\nB,A02-03-1,5\n")
	picks := Make(list, idx).Waves[0].Picks
	if picks[0].SKU != "A" || picks[0].Order != "K-1" || picks[1].Order != "K-2" || picks[2].SKU != "B" {
		t.Fatalf("picks %+v", picks)
	}
}
