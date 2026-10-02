// Package charges is the permit charge rule (docs/permit-charges.md): the one place the website quote, the
// renewal letters, and the forecast get it from.
package charges

import "fmt"

// Band is one CO2 band: vehicles emitting up to UpTo g/km (the top band has UpTo 0, no limit), and its
// charge in pence.
type Band struct {
	Name  string
	UpTo  int
	Pence int
}

// Bands are the CO2 bands, lowest first.
var Bands = []Band{
	{"A", 100, 3200},
	{"B", 120, 5800},
	{"C", 150, 9600},
	{"D", 185, 14200},
	{"E", 225, 18800},
	{"F", 255, 23600},
	{"G", 0, 29000},
}

const (
	DieselSurcharge = 4500 // pence
	ExtraPermit     = 6000 // pence, for the second and later permits at an address
)

// BandFor gives the band a vehicle emitting co2 g/km is in, and its label ("151 to 185 g/km"). A vehicle
// exactly on a band's upper figure is in that band.
func BandFor(co2 int) (Band, string) {
	lower := 0
	for _, b := range Bands {
		if b.UpTo == 0 || co2 <= b.UpTo {
			return b, span(lower, b.UpTo)
		}
		lower = b.UpTo + 1
	}
	panic("the top band has no limit")
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

// Surcharges gives what a permit pays on top of its band charge.
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
	b, _ := BandFor(co2)
	diesel, extra := Surcharges(fuel, household)
	return b.Name, b.Pence + diesel + extra
}
