// Command pickctl is the warehouse's command-line tool for the morning's picking.
//
//	pickctl stock STOCK.csv            the stock count in walking order
//	pickctl check ORDERS.csv STOCK.csv the night's orders checked against the stock count
package main

import (
	"fmt"
	"io"
	"os"

	"kestrel.example/pickctl/internal/orders"
	"kestrel.example/pickctl/internal/stock"
)

const usage = `usage:
  pickctl stock STOCK.csv
  pickctl check ORDERS.csv STOCK.csv
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	switch {
	case args[0] == "stock" && len(args) == 2:
		return cmdStock(args[1], stdout, stderr)
	case args[0] == "check" && len(args) == 3:
		return cmdCheck(args[1], args[2], stdout, stderr)
	}
	fmt.Fprint(stderr, usage)
	return 2
}

func fail(stderr io.Writer, err error) int {
	fmt.Fprintf(stderr, "pickctl: %v\n", err)
	return 1
}

func loadStock(path string) ([]stock.Item, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return stock.Load(f)
}

func loadOrders(path string) ([]orders.Order, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return orders.Load(f)
}

func cmdStock(path string, stdout, stderr io.Writer) int {
	items, err := loadStock(path)
	if err != nil {
		return fail(stderr, err)
	}
	stock.WalkOrder(items)
	for _, it := range items {
		fmt.Fprintf(stdout, "%s %s %d\n", it.Bin, it.SKU, it.OnHand)
	}
	return 0
}

func cmdCheck(ordersPath, stockPath string, stdout, stderr io.Writer) int {
	items, err := loadStock(stockPath)
	if err != nil {
		return fail(stderr, err)
	}
	idx, err := stock.Index(items)
	if err != nil {
		return fail(stderr, err)
	}
	list, err := loadOrders(ordersPath)
	if err != nil {
		return fail(stderr, err)
	}
	problems, lines, units := 0, 0, 0
	for _, o := range list {
		for n, l := range o.Lines {
			lines++
			units += l.Qty
			if _, ok := idx[l.SKU]; !ok {
				fmt.Fprintf(stdout, "order %s line %d: unknown sku %s\n", o.ID, n+1, l.SKU)
				problems++
			}
		}
	}
	if problems > 0 {
		fmt.Fprintf(stdout, "%d problems\n", problems)
		return 1
	}
	fmt.Fprintf(stdout, "ok: %d orders, %d lines, %d units\n", len(list), lines, units)
	return 0
}
