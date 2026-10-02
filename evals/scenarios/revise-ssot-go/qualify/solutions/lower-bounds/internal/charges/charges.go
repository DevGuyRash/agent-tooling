// Package charges is the permit charge rule (docs/permit-charges.md): the one place the website quote, the
// renewal letters, and the forecast get it from.
package charges

import "fmt"

// Band is one CO2 band: vehicles emitting From g/km or more, up to where the next band starts, and its
// charge in pence.
type Band struct {
	Name  string
	From  int
	Pence int
}

// Bands are the CO2 bands, lowest first, as the charges page lists them.
var Bands = []Band{
	{"A", 0, 3200},
	{"B", 101, 5800},
	{"C", 121, 9600},
	{"D", 151, 14200},
	{"E", 186, 18800},
	{"F", 226, 23600},
	{"G", 256, 29200},
}

const (
	DieselSurcharge = 4500 // pence
	ExtraPermit     = 6000 // pence, for the second and later permits at an address
)

// BandFor gives the band a vehicle emitting co2 g/km is in, and its label ("151 to 185 g/km").
func BandFor(co2 int) (Band, string) {
	for i := len(Bands) - 1; i >= 0; i-- {
		b := Bands[i]
		if co2 >= b.From {
			switch {
			case i == len(Bands)-1:
				return b, fmt.Sprintf("over %d g/km", b.From-1)
			case b.From == 0:
				return b, fmt.Sprintf("up to %d g/km", Bands[i+1].From-1)
			default:
				return b, fmt.Sprintf("%d to %d g/km", b.From, Bands[i+1].From-1)
			}
		}
	}
	panic("the lowest band starts at 0")
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
