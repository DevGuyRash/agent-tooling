// Package money formats amounts, which are whole pence everywhere in permitctl.
package money

import "fmt"

// Format gives "96.00" for 9600 pence.
func Format(pence int) string {
	return fmt.Sprintf("%d.%02d", pence/100, pence%100)
}
