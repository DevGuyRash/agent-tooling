// Package table lays out plain-text tables: columns two spaces apart, each as wide as its widest cell in
// characters (runes), the last column never padded.
package table

import (
	"strings"
	"unicode/utf8"
)

// Render returns the header and rows, one line each; right[i] right-aligns column i.
func Render(header []string, right []bool, rows [][]string) string {
	widths := make([]int, len(header))
	for _, r := range append([][]string{header}, rows...) {
		for i, c := range r {
			widths[i] = max(widths[i], utf8.RuneCountInString(c))
		}
	}
	var b strings.Builder
	for _, r := range append([][]string{header}, rows...) {
		for i, c := range r {
			if i == len(r)-1 {
				b.WriteString(c)
				break
			}
			pad := strings.Repeat(" ", widths[i]-utf8.RuneCountInString(c))
			if right[i] {
				b.WriteString(pad + c)
			} else {
				b.WriteString(c + pad)
			}
			b.WriteString("  ")
		}
		b.WriteString("\n")
	}
	return b.String()
}
