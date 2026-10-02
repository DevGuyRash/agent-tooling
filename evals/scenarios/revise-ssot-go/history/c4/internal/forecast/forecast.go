// Package forecast works out next year's permit income for the budget, as if every permit renews once at
// the current charges.
package forecast

import (
	"fmt"
	"strings"

	"permitctl/internal/money"
	"permitctl/internal/permits"
)

// Permit charges by CO2 band (docs/permit-charges.md). limit is the band's highest g/km; 0 for the top band.
var bands = []struct {
	name  string
	limit int
	pence int
}{
	{"A", 100, 3200},
	{"B", 120, 5800},
	{"C", 150, 9600},
	{"D", 185, 14200},
	{"E", 225, 18800},
	{"F", 0, 23600},
}

const (
	diesel      = 3000 // pence
	extraPermit = 5000 // pence, second and later permits at an address
)

func bandOf(co2 int) int {
	for i, b := range bands {
		if b.limit == 0 || co2 < b.limit {
			return i
		}
	}
	return len(bands) - 1
}

// Table gives the number of permits and their renewal income by band, and the totals.
func Table(all []permits.Permit) string {
	counts := make([]int, len(bands))
	income := make([]int, len(bands))
	for _, p := range all {
		i := bandOf(p.CO2)
		pence := bands[i].pence
		if p.Fuel == "diesel" {
			pence += diesel
		}
		if p.Household > 1 {
			pence += extraPermit
		}
		counts[i]++
		income[i] += pence
	}
	var b strings.Builder
	fmt.Fprintf(&b, "%-5s %7s %10s\n", "band", "permits", "income")
	n, sum := 0, 0
	for i, x := range bands {
		fmt.Fprintf(&b, "%-5s %7d %10s\n", x.name, counts[i], money.Format(income[i]))
		n += counts[i]
		sum += income[i]
	}
	fmt.Fprintf(&b, "%-5s %7d %10s\n", "total", n, money.Format(sum))
	return b.String()
}
