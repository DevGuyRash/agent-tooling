// Package sales reads the box office's sales export (docs/sales-export.md).
package sales

import (
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"regexp"
	"strings"
)

// Row is one line of the export: one sale, or one reissue of a pass sold earlier.
type Row struct {
	Line   int // line in the file; the header is line 1
	Order  string
	PassID string
	Zone   string
	Holder string
}

// Zones are the ground's entry zones; every pass belongs to one.
var Zones = map[string]bool{"NORTH": true, "SOUTH": true, "EAST": true, "WEST": true, "FAMILY": true,
	"HOSPITALITY": true}

var passPattern = regexp.MustCompile(`^P-[0-9]{6}$`)

var columns = []string{"order_id", "pass_id", "zone", "holder"}

// Read parses an export: a header naming at least order_id, pass_id, zone, and holder (in any order, other
// columns ignored), then one row per sale in the order the box office made them. Any malformed row is an
// error naming its line, and nothing is returned.
func Read(r io.Reader) ([]Row, error) {
	cr := csv.NewReader(r)
	cr.FieldsPerRecord = -1
	header, err := cr.Read()
	if errors.Is(err, io.EOF) {
		return nil, errors.New("empty export: no header")
	}
	if err != nil {
		return nil, fmt.Errorf("line 1: %v", err)
	}
	at := map[string]int{}
	for i, name := range header {
		at[strings.TrimSpace(strings.ToLower(name))] = i
	}
	for _, c := range columns {
		if _, ok := at[c]; !ok {
			return nil, fmt.Errorf("line 1: no %s column", c)
		}
	}
	var rows []Row
	for {
		rec, err := cr.Read()
		if errors.Is(err, io.EOF) {
			return rows, nil
		}
		if err != nil {
			var pe *csv.ParseError
			if errors.As(err, &pe) {
				return nil, fmt.Errorf("line %d: %v", pe.Line, pe.Err)
			}
			return nil, err
		}
		line, _ := cr.FieldPos(0)
		get := func(c string) string {
			if i := at[c]; i < len(rec) {
				return strings.TrimSpace(rec[i])
			}
			return ""
		}
		row := Row{Line: line, Order: get("order_id"), PassID: get("pass_id"), Zone: strings.ToUpper(get("zone")),
			Holder: get("holder")}
		switch {
		case !passPattern.MatchString(row.PassID):
			return nil, fmt.Errorf("line %d: bad pass_id %q", line, row.PassID)
		case !Zones[row.Zone]:
			return nil, fmt.Errorf("line %d: unknown zone %q", line, row.Zone)
		case row.Order == "":
			return nil, fmt.Errorf("line %d: no order_id", line)
		}
		rows = append(rows, row)
	}
}
