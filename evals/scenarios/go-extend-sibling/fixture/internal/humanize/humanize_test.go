package humanize

import "testing"

func TestBytes(t *testing.T) {
	cases := []struct {
		n    int64
		want string
	}{
		{0, "0 B"},
		{1, "1 B"},
		{1023, "1023 B"},
		{1024, "1.0 KiB"},
		{1536, "1.5 KiB"},
		{1203332, "1.1 MiB"},
		{1834201923, "1.7 GiB"},
		{5 << 40, "5.0 TiB"},
		{3 << 50, "3.0 PiB"},
		{2048 << 50, "2048.0 PiB"},
	}
	for _, c := range cases {
		if got := Bytes(c.n); got != c.want {
			t.Errorf("Bytes(%d) = %q, want %q", c.n, got, c.want)
		}
	}
}
