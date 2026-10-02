// Package quote works out what a resident parking permit costs, for the permit application form on the
// council website.
package quote

import (
	"fmt"

	"permitctl/internal/charges"
)

// Line is one line of a quote.
type Line struct {
	Label string
	Pence int
}

// Quote is the charge for one permit, line by line.
type Quote struct {
	Band  string
	Lines []Line
	Total int
}

// For works out the charge for a vehicle emitting co2 g/km, running on fuel, as the household-th permit at
// its address.
func For(co2 int, fuel string, household int) Quote {
	b, span := charges.BandFor(co2)
	q := Quote{Band: b.Name, Lines: []Line{{fmt.Sprintf("Band %s (%s)", b.Name, span), b.Pence}}}
	diesel, extra := charges.Surcharges(fuel, household)
	if diesel != 0 {
		q.Lines = append(q.Lines, Line{"Diesel surcharge", diesel})
	}
	if extra != 0 {
		q.Lines = append(q.Lines, Line{"Second permit at the address", extra})
	}
	for _, l := range q.Lines {
		q.Total += l.Pence
	}
	return q
}
