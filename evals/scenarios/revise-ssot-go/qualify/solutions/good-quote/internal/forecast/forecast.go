// Package forecast works out next year's permit income for the budget, as if every permit renews once at
// the current charges.
package forecast

import (
	"fmt"
	"strings"

	"permitctl/internal/money"
	"permitctl/internal/permits"
	"permitctl/internal/quote"
)

// Table gives the number of permits and their renewal income by band, and the totals.
func Table(all []permits.Permit) string {
	counts := map[string]int{}
	income := map[string]int{}
	for _, p := range all {
		band, pence := quote.Charge(p.CO2, p.Fuel, p.Household)
		counts[band]++
		income[band] += pence
	}
	var b strings.Builder
	fmt.Fprintf(&b, "%-5s %7s %10s\n", "band", "permits", "income")
	n, sum := 0, 0
	for _, x := range quote.Bands {
		fmt.Fprintf(&b, "%-5s %7d %10s\n", x.Name, counts[x.Name], money.Format(income[x.Name]))
		n += counts[x.Name]
		sum += income[x.Name]
	}
	fmt.Fprintf(&b, "%-5s %7d %10s\n", "total", n, money.Format(sum))
	return b.String()
}
