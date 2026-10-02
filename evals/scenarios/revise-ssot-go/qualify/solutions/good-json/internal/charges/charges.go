// Package charges is the permit charge rule, read from charges.json (docs/permit-charges.md), which is
// compiled into the program.
package charges

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

//go:embed charges.json
var schedule []byte

// Band is one CO2 band: vehicles emitting up to UpTo g/km (0 for the top band, no limit), and its charge.
type Band struct {
	Name  string
	UpTo  int
	Pence int
}

var (
	// Bands are the CO2 bands, lowest first.
	Bands []Band
	// DieselSurcharge and ExtraPermit are in pence.
	DieselSurcharge, ExtraPermit int
)

func pence(pounds string) int {
	whole, frac, _ := strings.Cut(pounds, ".")
	w, err1 := strconv.Atoi(whole)
	f, err2 := strconv.Atoi((frac + "00")[:2])
	if err1 != nil || err2 != nil {
		panic(fmt.Sprintf("charges.json: %q is not an amount", pounds))
	}
	return w*100 + f
}

func init() {
	var s struct {
		Bands []struct {
			Band   string `json:"band"`
			UpTo   int    `json:"up_to_g_km"`
			Charge string `json:"charge"`
		} `json:"bands"`
		Diesel string `json:"diesel_surcharge"`
		Extra  string `json:"second_permit_surcharge"`
	}
	if err := json.Unmarshal(schedule, &s); err != nil {
		panic("charges.json: " + err.Error())
	}
	for _, b := range s.Bands {
		Bands = append(Bands, Band{b.Band, b.UpTo, pence(b.Charge)})
	}
	DieselSurcharge, ExtraPermit = pence(s.Diesel), pence(s.Extra)
}

// BandFor gives the band a vehicle emitting co2 g/km is in, and its label. A vehicle exactly on a band's
// upper figure is in that band.
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
