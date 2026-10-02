package money

import "testing"

func TestFormat(t *testing.T) {
	for pence, want := range map[int]string{0: "0.00", 5: "0.05", 3200: "32.00", 14250: "142.50", 1234567: "12345.67"} {
		if got := Format(pence); got != want {
			t.Errorf("Format(%d) = %q, want %q", pence, got, want)
		}
	}
}
