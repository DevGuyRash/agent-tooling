// Package humanize formats sizes for bakctl's reports.
package humanize

import "fmt"

var units = []string{"KiB", "MiB", "GiB", "TiB", "PiB"}

// Bytes formats n as bakctl prints sizes: "0 B" to "1023 B" exactly, then the largest binary unit
// (KiB, MiB, GiB, TiB, PiB) that keeps the value under 1024, with one decimal place.
func Bytes(n int64) string {
	if n < 1024 {
		return fmt.Sprintf("%d B", n)
	}
	v := float64(n) / 1024
	i := 0
	for v >= 1024 && i < len(units)-1 {
		v /= 1024
		i++
	}
	return fmt.Sprintf("%.1f %s", v, units[i])
}
