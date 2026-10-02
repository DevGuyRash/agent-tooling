// Package renewals lists the permits due for renewal in a month, with what each renewal costs, for the
// renewal letters.
package renewals

import (
	"fmt"
	"sort"
	"strings"
	"time"

	"permitctl/internal/money"
	"permitctl/internal/permits"
)

// charge is the renewal charge for a permit, by its CO2 band (docs/permit-charges.md).
func charge(p permits.Permit) (string, int) {
	var band string
	var pence int
	switch {
	case p.CO2 <= 100:
		band, pence = "A", 3200
	case p.CO2 <= 120:
		band, pence = "B", 5800
	case p.CO2 <= 150:
		band, pence = "C", 9600
	case p.CO2 <= 185:
		band, pence = "D", 14200
	case p.CO2 <= 225:
		band, pence = "E", 18800
	case p.CO2 <= 255:
		band, pence = "F", 23600
	default:
		band, pence = "G", 29200
	}
	if p.Fuel == "diesel" {
		pence += 4500
	}
	if p.Household > 1 {
		pence += 6000
	}
	return band, pence
}

// Letters lists the permits expiring in month, by expiry date and then permit number, and the total.
func Letters(all []permits.Permit, month time.Time) string {
	var due []permits.Permit
	for _, p := range all {
		if p.Expires.Year() == month.Year() && p.Expires.Month() == month.Month() {
			due = append(due, p)
		}
	}
	label := month.Format("2006-01")
	if len(due) == 0 {
		return fmt.Sprintf("No renewals due in %s.\n", label)
	}
	sort.Slice(due, func(i, j int) bool {
		if !due[i].Expires.Equal(due[j].Expires) {
			return due[i].Expires.Before(due[j].Expires)
		}
		return due[i].ID < due[j].ID
	})
	var b strings.Builder
	total := 0
	for _, p := range due {
		band, pence := charge(p)
		notes := ""
		if p.Fuel == "diesel" {
			notes += ", diesel"
		}
		if p.Household > 1 {
			notes += ", second permit"
		}
		fmt.Fprintf(&b, "%s %s (%s): band %s%s, %s\n", p.ID, p.VRM, p.Address, band, notes, money.Format(pence))
		total += pence
	}
	s := "s"
	if len(due) == 1 {
		s = ""
	}
	fmt.Fprintf(&b, "%d renewal%s due in %s, %s in total\n", len(due), s, label, money.Format(total))
	return b.String()
}
