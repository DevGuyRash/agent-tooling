// Package orders reads the night's order export.
package orders

import (
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
	"time"
)

// Line is one order line: a SKU and how many units of it.
type Line struct {
	SKU string
	Qty int
}

// Order is one customer order with its lines in the order the customer added them.
type Order struct {
	ID       string
	PlacedAt time.Time
	Lines    []Line
}

// Units is the order's total quantity.
func (o Order) Units() int {
	n := 0
	for _, l := range o.Lines {
		n += l.Qty
	}
	return n
}

// Load reads the export: a CSV with the header order_id,placed_at,sku,qty, one row per order line, placed_at
// in RFC 3339 (the shop exports UTC). An order's rows need not be next to each other; orders come back in
// the order of their first row, each order's lines in file order.
func Load(r io.Reader) ([]Order, error) {
	cr := csv.NewReader(r)
	cr.FieldsPerRecord = 4
	header, err := cr.Read()
	if err != nil {
		return nil, fmt.Errorf("orders: %w", err)
	}
	if strings.Join(header, ",") != "order_id,placed_at,sku,qty" {
		return nil, errors.New("orders: header must be order_id,placed_at,sku,qty")
	}
	var list []Order
	at := map[string]int{}
	for {
		rec, err := cr.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("orders: %w", err)
		}
		line, _ := cr.FieldPos(0)
		if rec[0] == "" || rec[2] == "" {
			return nil, fmt.Errorf("orders line %d: empty order_id or sku", line)
		}
		placed, err := time.Parse(time.RFC3339, rec[1])
		if err != nil {
			return nil, fmt.Errorf("orders line %d: bad placed_at %q", line, rec[1])
		}
		qty, err := strconv.Atoi(rec[3])
		if err != nil || qty < 1 {
			return nil, fmt.Errorf("orders line %d: bad qty %q", line, rec[3])
		}
		i, seen := at[rec[0]]
		if !seen {
			i = len(list)
			at[rec[0]] = i
			list = append(list, Order{ID: rec[0], PlacedAt: placed})
		} else if !list[i].PlacedAt.Equal(placed) {
			return nil, fmt.Errorf("orders line %d: order %s has two placed_at times", line, rec[0])
		}
		list[i].Lines = append(list[i].Lines, Line{SKU: rec[2], Qty: qty})
	}
	return list, nil
}
