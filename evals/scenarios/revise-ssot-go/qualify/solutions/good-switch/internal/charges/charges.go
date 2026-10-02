// Package charges is the permit charge rule (docs/permit-charges.md), used by the quote, the renewal letters,
// and the forecast.
package charges

import "fmt"

// The highest g/km of each band but the top one.
const (
	topA = 100
	topB = 120
	topC = 150
	topD = 185
	topE = 225
	topF = 255
)

const (
	DieselSurcharge = 4500 // pence
	ExtraPermit     = 6000 // pence
)

// Band is a CO2 band as a vehicle's charge shows it.
type Band struct {
	Name  string
	Label string
	Pence int
}

// Names are the bands in order, for the forecast's table.
var Names = []string{"A", "B", "C", "D", "E", "F", "G"}

func between(name string, low, high, pence int) Band {
	return Band{name, fmt.Sprintf("%d to %d g/km", low+1, high), pence}
}

// BandFor gives the band a vehicle emitting co2 g/km is in; one exactly on a band's figure is in that band.
func BandFor(co2 int) Band {
	switch {
	case co2 <= topA:
		return Band{"A", fmt.Sprintf("up to %d g/km", topA), 3200}
	case co2 <= topB:
		return between("B", topA, topB, 5800)
	case co2 <= topC:
		return between("C", topB, topC, 9600)
	case co2 <= topD:
		return between("D", topC, topD, 14200)
	case co2 <= topE:
		return between("E", topD, topE, 18800)
	case co2 <= topF:
		return between("F", topE, topF, 23600)
	default:
		return Band{"G", fmt.Sprintf("over %d g/km", topF), 29200}
	}
}

// Surcharges gives what a permit pays on top of its band charge: 0 for a surcharge that does not apply.
func Surcharges(fuel string, household int) (diesel, extra int) {
	if fuel == "diesel" {
		diesel = DieselSurcharge
	}
	if household > 1 {
		extra = ExtraPermit
	}
	return diesel, extra
}

// Charge is a permit's whole charge in pence, and its band.
func Charge(co2 int, fuel string, household int) (string, int) {
	b := BandFor(co2)
	diesel, extra := Surcharges(fuel, household)
	return b.Name, b.Pence + diesel + extra
}
