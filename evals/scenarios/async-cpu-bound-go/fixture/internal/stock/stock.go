// Package stock reads the warehouse's stock count and knows how the pickers walk the bins.
package stock

import (
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"sort"
	"strconv"
	"strings"
)

// Bin is a shelf position, written A03-12-2: aisle 3, bay 12, level 2.
type Bin struct {
	Aisle, Bay, Level int
}

// ParseBin reads a bin label such as "A03-12-2".
func ParseBin(s string) (Bin, error) {
	var b Bin
	parts := strings.Split(s, "-")
	if len(parts) != 3 || len(parts[0]) < 2 || parts[0][0] != 'A' {
		return b, fmt.Errorf("bad bin %q (want A<aisle>-<bay>-<level>)", s)
	}
	nums := []string{parts[0][1:], parts[1], parts[2]}
	vals := make([]int, 3)
	for i, n := range nums {
		v, err := strconv.Atoi(n)
		if err != nil || v < 1 {
			return b, fmt.Errorf("bad bin %q (want A<aisle>-<bay>-<level>)", s)
		}
		vals[i] = v
	}
	return Bin{Aisle: vals[0], Bay: vals[1], Level: vals[2]}, nil
}

func (b Bin) String() string {
	return fmt.Sprintf("A%02d-%02d-%d", b.Aisle, b.Bay, b.Level)
}

// WalkBefore reports whether a picker reaches bin a before bin b: aisle by aisle, up the odd aisles (bays
// ascending) and down the even ones (bays descending), lower levels first within a bay.
func WalkBefore(a, b Bin) bool {
	if a.Aisle != b.Aisle {
		return a.Aisle < b.Aisle
	}
	if a.Bay != b.Bay {
		if a.Aisle%2 == 1 {
			return a.Bay < b.Bay
		}
		return a.Bay > b.Bay
	}
	return a.Level < b.Level
}

// Item is one SKU's line in the stock count.
type Item struct {
	SKU    string
	Bin    Bin
	OnHand int
}

// Load reads a stock count: a CSV with the header sku,bin,on_hand.
func Load(r io.Reader) ([]Item, error) {
	cr := csv.NewReader(r)
	cr.FieldsPerRecord = 3
	header, err := cr.Read()
	if err != nil {
		return nil, fmt.Errorf("stock: %w", err)
	}
	if strings.Join(header, ",") != "sku,bin,on_hand" {
		return nil, errors.New("stock: header must be sku,bin,on_hand")
	}
	var items []Item
	for {
		rec, err := cr.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("stock: %w", err)
		}
		line, _ := cr.FieldPos(0)
		bin, err := ParseBin(rec[1])
		if err != nil {
			return nil, fmt.Errorf("stock line %d: %w", line, err)
		}
		n, err := strconv.Atoi(rec[2])
		if err != nil || n < 0 {
			return nil, fmt.Errorf("stock line %d: bad on_hand %q", line, rec[2])
		}
		if rec[0] == "" {
			return nil, fmt.Errorf("stock line %d: empty sku", line)
		}
		items = append(items, Item{SKU: rec[0], Bin: bin, OnHand: n})
	}
	return items, nil
}

// Index maps each SKU to its item, and fails on a SKU listed twice.
func Index(items []Item) (map[string]Item, error) {
	idx := make(map[string]Item, len(items))
	for _, it := range items {
		if _, dup := idx[it.SKU]; dup {
			return nil, fmt.Errorf("stock lists %s twice", it.SKU)
		}
		idx[it.SKU] = it
	}
	return idx, nil
}

// WalkOrder sorts items in the order a picker reaches their bins, SKUs in the same bin by name.
func WalkOrder(items []Item) {
	sort.SliceStable(items, func(i, j int) bool {
		if items[i].Bin != items[j].Bin {
			return WalkBefore(items[i].Bin, items[j].Bin)
		}
		return items[i].SKU < items[j].SKU
	})
}
