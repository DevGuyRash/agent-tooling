package stock

import (
	"strings"
	"testing"
)

func TestParseBin(t *testing.T) {
	b, err := ParseBin("A03-12-2")
	if err != nil || b != (Bin{3, 12, 2}) || b.String() != "A03-12-2" {
		t.Fatalf("got %v, %v", b, err)
	}
	for _, bad := range []string{"", "B03-12-2", "A3-12", "A03-x-2", "A00-01-1"} {
		if _, err := ParseBin(bad); err == nil {
			t.Errorf("%q: no error", bad)
		}
	}
}

func TestWalkBefore(t *testing.T) {
	cases := []struct {
		a, b string
		want bool
	}{
		{"A01-03-1", "A01-04-1", true},  // up an odd aisle
		{"A02-04-1", "A02-03-1", true},  // down an even aisle
		{"A01-20-4", "A02-01-1", true},  // aisle first
		{"A03-05-1", "A03-05-2", true},  // lower level first
		{"A03-05-2", "A03-05-2", false}, // the same bin
	}
	for _, c := range cases {
		a, _ := ParseBin(c.a)
		b, _ := ParseBin(c.b)
		if got := WalkBefore(a, b); got != c.want {
			t.Errorf("WalkBefore(%s, %s) = %v", c.a, c.b, got)
		}
	}
}

func TestLoadAndIndex(t *testing.T) {
	items, err := Load(strings.NewReader("sku,bin,on_hand\nTENT-2P,A01-03-1,6\nMUG-TI,A02-11-1,0\n"))
	if err != nil || len(items) != 2 || items[1] != (Item{"MUG-TI", Bin{2, 11, 1}, 0}) {
		t.Fatalf("got %v, %v", items, err)
	}
	if _, err := Index(append(items, items[0])); err == nil {
		t.Error("a SKU listed twice was accepted")
	}
	if _, err := Load(strings.NewReader("sku,bin,on_hand\nTENT-2P,A01-03-1,-1\n")); err == nil {
		t.Error("negative on_hand accepted")
	}
}
