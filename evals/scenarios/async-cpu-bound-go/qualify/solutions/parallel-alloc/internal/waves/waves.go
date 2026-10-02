// Package waves plans the morning's picking waves from the night's orders and the stock count, by the rules in
// docs/waves.md.
package waves

import (
	"sort"
	"sync"

	"kestrel.example/pickctl/internal/orders"
	"kestrel.example/pickctl/internal/stock"
)

// Cart limits.
const (
	CartOrders = 12
	CartUnits  = 60
)

// Pick is one line of a cart's pick list.
type Pick struct {
	Bin   stock.Bin
	SKU   string
	Units int
	Order string
	seq   int // the order's place in the sequence
	line  int // the line's place in its order
}

// Short is an order line that could not get all its units.
type Short struct {
	Order string
	SKU   string
	Units int
}

// Wave is one cart.
type Wave struct {
	Orders int
	Units  int
	Picks  []Pick
}

// Plan is the morning's picking.
type Plan struct {
	Waves []Wave
	Short []Short
}

// Sequence returns the orders first come, first served: by placed time, then by order ID.
func Sequence(list []orders.Order) []orders.Order {
	seq := append([]orders.Order(nil), list...)
	sort.SliceStable(seq, func(i, j int) bool {
		if !seq[i].PlacedAt.Equal(seq[j].PlacedAt) {
			return seq[i].PlacedAt.Before(seq[j].PlacedAt)
		}
		return seq[i].ID < seq[j].ID
	})
	return seq
}

// Make allocates the stock to the orders in sequence, puts the orders that got anything on carts, and sorts
// each cart's pick list in walking order. Every order line's SKU must be in idx.
func Make(list []orders.Order, idx map[string]stock.Item) Plan {
	left := make(map[string]int, len(idx))
	for sku, it := range idx {
		left[sku] = it.OnHand
	}
	// Orders are independent until they touch the shared stock, so each order is allocated in its own
	// goroutine, with the stock behind a mutex; results are kept by sequence so the carts come out in order.
	type result struct {
		picks []Pick
		units int
		short []Short
	}
	seq := Sequence(list)
	results := make([]result, len(seq))
	var mu sync.Mutex
	var wg sync.WaitGroup
	for i, o := range seq {
		wg.Add(1)
		go func(i int, o orders.Order) {
			defer wg.Done()
			var r result
			mu.Lock()
			for n, l := range o.Lines {
				take := min(l.Qty, left[l.SKU])
				left[l.SKU] -= take
				if take > 0 {
					r.picks = append(r.picks, Pick{Bin: idx[l.SKU].Bin, SKU: l.SKU, Units: take, Order: o.ID, seq: i, line: n})
					r.units += take
				}
				if l.Qty > take {
					r.short = append(r.short, Short{Order: o.ID, SKU: l.SKU, Units: l.Qty - take})
				}
			}
			mu.Unlock()
			results[i] = r
		}(i, o)
	}
	wg.Wait()
	var plan Plan
	for _, r := range results {
		plan.Short = append(plan.Short, r.short...)
		if len(r.picks) == 0 {
			continue
		}
		last := len(plan.Waves) - 1
		if last < 0 || plan.Waves[last].Orders == CartOrders || plan.Waves[last].Units+r.units > CartUnits {
			plan.Waves = append(plan.Waves, Wave{})
			last++
		}
		w := &plan.Waves[last]
		w.Orders++
		w.Units += r.units
		w.Picks = append(w.Picks, r.picks...)
	}
	for i := range plan.Waves {
		picks := plan.Waves[i].Picks
		sort.Slice(picks, func(a, b int) bool {
			pa, pb := picks[a], picks[b]
			if pa.Bin != pb.Bin {
				return stock.WalkBefore(pa.Bin, pb.Bin)
			}
			if pa.seq != pb.seq {
				return pa.seq < pb.seq
			}
			return pa.line < pb.line
		})
	}
	return plan
}
