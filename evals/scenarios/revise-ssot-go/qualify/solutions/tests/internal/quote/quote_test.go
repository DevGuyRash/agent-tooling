package quote

import (
	"reflect"
	"testing"
)

func TestDieselBandD(t *testing.T) {
	got := For(163, "diesel", 1)
	want := Quote{Band: "D", Lines: []Line{{"Band D (151 to 185 g/km)", 14200}, {"Diesel surcharge", 4500}}, Total: 18700}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("got %+v, want %+v", got, want)
	}
}

func TestBandLabels(t *testing.T) {
	for co2, want := range map[int]string{0: "Band A (up to 100 g/km)", 112: "Band B (101 to 120 g/km)",
		199: "Band E (186 to 225 g/km)", 241: "Band F (226 to 255 g/km)", 256: "Band G (over 255 g/km)"} {
		if got := For(co2, "petrol", 1).Lines[0].Label; got != want {
			t.Errorf("co2 %d: %q, want %q", co2, got, want)
		}
	}
}
