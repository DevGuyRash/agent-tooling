// Package forecast works out next year's permit income for the budget, as if every permit renews once at
// the current charges.
package forecast

import (
	"fmt"
	"strings"

	"permitctl/internal/charges"
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
	extraPermit = 6000 // pence, second and later permits at an address
)

// Table gives the number of permits and their renewal income by band, and the totals.
func Table(all []permits.Permit) string {
	counts := map[string]int{}
	income := map[string]int{}
	for _, p := range all {
		band, pence := charges.Charge(p.CO2, p.Fuel, p.Household)
		counts[band]++
		income[band] += pence
	}
	var b strings.Builder
	fmt.Fprintf(&b, "%-5s %7s %10s\n", "band", "permits", "income")
	n, sum := 0, 0
	for _, x := range charges.Bands {
		fmt.Fprintf(&b, "%-5s %7d %10s\n", x.Name, counts[x.Name], money.Format(income[x.Name]))
		n += counts[x.Name]
		sum += income[x.Name]
	}
	fmt.Fprintf(&b, "%-5s %7d %10s\n", "total", n, money.Format(sum))
	return b.String()
}
