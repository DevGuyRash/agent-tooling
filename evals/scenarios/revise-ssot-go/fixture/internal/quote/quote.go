// Package quote works out what a resident parking permit costs, for the permit application form on the
// council website.
package quote

import "fmt"

// band is one CO2 band of the permit charges (docs/permit-charges.md): vehicles emitting up to upTo g/km,
// the top band with no limit (upTo 0), and the band's charge in pence.
type band struct {
	name  string
	upTo  int
	pence int
}

var bands = []band{
	{"A", 100, 3200},
	{"B", 120, 5800},
	{"C", 150, 9600},
	{"D", 185, 14200},
	{"E", 225, 18800},
	{"F", 0, 23600},
}

const (
	dieselSurcharge = 3000 // pence
	extraPermit     = 5000 // pence, for the second and later permits at an address
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
	b, lower := bands[len(bands)-1], 0
	for _, x := range bands {
		if x.upTo == 0 || co2 <= x.upTo {
			b = x
			break
		}
		lower = x.upTo + 1
	}
	q := Quote{Band: b.name}
	q.Lines = append(q.Lines, Line{fmt.Sprintf("Band %s (%s)", b.name, span(lower, b.upTo)), b.pence})
	if fuel == "diesel" {
		q.Lines = append(q.Lines, Line{"Diesel surcharge", dieselSurcharge})
	}
	if household > 1 {
		q.Lines = append(q.Lines, Line{"Second permit at the address", extraPermit})
	}
	for _, l := range q.Lines {
		q.Total += l.Pence
	}
	return q
}

func span(lower, upTo int) string {
	switch {
	case upTo == 0:
		return fmt.Sprintf("over %d g/km", lower-1)
	case lower == 0:
		return fmt.Sprintf("up to %d g/km", upTo)
	default:
		return fmt.Sprintf("%d to %d g/km", lower, upTo)
	}
}
