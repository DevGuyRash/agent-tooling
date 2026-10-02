package permits

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestRead(t *testing.T) {
	all, err := Read("testdata/permits.csv")
	if err != nil {
		t.Fatal(err)
	}
	if len(all) != 6 {
		t.Fatalf("read %d permits, want 6", len(all))
	}
	want := Permit{ID: "FV-10442", Address: "14 Orchard Row", VRM: "KX19 TRV", CO2: 163, Fuel: "diesel", Household: 1,
		Expires: time.Date(2027, 4, 9, 0, 0, 0, 0, time.UTC)}
	if all[0] != want {
		t.Errorf("first permit = %+v, want %+v", all[0], want)
	}
}

func write(t *testing.T, text string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "permits.csv")
	if err := os.WriteFile(p, []byte(text), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestReadAnyColumnOrder(t *testing.T) {
	p := write(t, "expires,fuel,co2,household_permit,vrm,address,permit_id\n"+
		" 2027-06-01 , Petrol ,140, 2 ,ab12 cde, 1 Mill Lane ,FV-1\n")
	all, err := Read(p)
	if err != nil {
		t.Fatal(err)
	}
	if got := all[0]; got.Fuel != "petrol" || got.VRM != "AB12 CDE" || got.Household != 2 || got.Address != "1 Mill Lane" {
		t.Errorf("got %+v", got)
	}
}

func TestReadErrors(t *testing.T) {
	const header = "permit_id,address,vrm,co2,fuel,household_permit,expires\n"
	for name, c := range map[string]struct{ text, want string }{
		"no column":    {"permit_id,address,vrm,co2,fuel,expires\n", "no household_permit column"},
		"bad co2":      {header + "FV-1,1 Mill Lane,AB12 CDE,lots,petrol,1,2027-06-01\n", "line 2: co2"},
		"negative co2": {header + "FV-1,1 Mill Lane,AB12 CDE,-4,petrol,1,2027-06-01\n", "line 2: co2"},
		"fuel":         {header + "FV-1,1 Mill Lane,AB12 CDE,140,lpg,1,2027-06-01\n", `unknown fuel "lpg"`},
		"household":    {header + "FV-1,1 Mill Lane,AB12 CDE,140,petrol,0,2027-06-01\n", "household_permit"},
		"date":         {header + "FV-1,1 Mill Lane,AB12 CDE,140,petrol,1,2027-06-31\n", "expires"},
		"empty":        {"", "empty file"},
	} {
		_, err := Read(write(t, c.text))
		if err == nil || !strings.Contains(err.Error(), c.want) {
			t.Errorf("%s: error %v, want one containing %q", name, err, c.want)
		}
	}
	if _, err := Read("testdata/missing.csv"); err == nil {
		t.Error("missing file: no error")
	}
}
