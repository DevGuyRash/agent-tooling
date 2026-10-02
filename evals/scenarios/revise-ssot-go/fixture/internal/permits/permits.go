// Package permits reads the permit system's nightly export, permits.csv (docs/permits-export.md).
package permits

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"
	"time"
)

// Fuels are the fuel types the permit system records.
var Fuels = []string{"petrol", "diesel", "hybrid", "electric"}

// Permit is one row of the export.
type Permit struct {
	ID        string
	Address   string
	VRM       string
	CO2       int // g/km, from the vehicle's V5C
	Fuel      string
	Household int // 1 for the address's first permit, 2 for its second, and so on
	Expires   time.Time
}

var columns = []string{"permit_id", "address", "vrm", "co2", "fuel", "household_permit", "expires"}

// IsFuel reports whether f is one of Fuels.
func IsFuel(f string) bool {
	for _, x := range Fuels {
		if f == x {
			return true
		}
	}
	return false
}

// Read reads an export. Columns may come in any order and values may have spaces around them.
func Read(path string) ([]Permit, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	header, err := r.Read()
	if err == io.EOF {
		return nil, fmt.Errorf("%s: empty file", path)
	}
	if err != nil {
		return nil, fmt.Errorf("%s: %v", path, err)
	}
	at := map[string]int{}
	for i, h := range header {
		// The permit system writes a byte-order mark before the header.
		at[strings.TrimSpace(strings.TrimPrefix(h, "\ufeff"))] = i
	}
	for _, c := range columns {
		if _, ok := at[c]; !ok {
			return nil, fmt.Errorf("%s: no %s column", path, c)
		}
	}
	var out []Permit
	for line := 2; ; line++ {
		rec, err := r.Read()
		if err == io.EOF {
			return out, nil
		}
		if err != nil {
			return nil, fmt.Errorf("%s: %v", path, err)
		}
		get := func(c string) string {
			if i := at[c]; i < len(rec) {
				return strings.TrimSpace(rec[i])
			}
			return ""
		}
		p, err := parse(get)
		if err != nil {
			return nil, fmt.Errorf("%s: line %d: %v", path, line, err)
		}
		out = append(out, p)
	}
}

func parse(get func(string) string) (Permit, error) {
	p := Permit{ID: get("permit_id"), Address: get("address"), VRM: strings.ToUpper(get("vrm")),
		Fuel: strings.ToLower(get("fuel"))}
	var err error
	if p.CO2, err = strconv.Atoi(get("co2")); err != nil || p.CO2 < 0 {
		return p, fmt.Errorf("co2 %q is not a number of g/km", get("co2"))
	}
	if !IsFuel(p.Fuel) {
		return p, fmt.Errorf("unknown fuel %q", get("fuel"))
	}
	if p.Household, err = strconv.Atoi(get("household_permit")); err != nil || p.Household < 1 {
		return p, fmt.Errorf("household_permit %q is not 1, 2, 3, ...", get("household_permit"))
	}
	if p.Expires, err = time.Parse("2006-01-02", get("expires")); err != nil {
		return p, fmt.Errorf("expires %q is not a date (YYYY-MM-DD)", get("expires"))
	}
	return p, nil
}
