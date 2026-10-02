package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func pickctl(t *testing.T, args ...string) (int, string, string) {
	t.Helper()
	var out, errb bytes.Buffer
	code := run(args, &out, &errb)
	return code, out.String(), errb.String()
}

func testdata(name string) string { return filepath.Join("..", "..", "testdata", name) }

func TestStockWalkOrder(t *testing.T) {
	code, out, _ := pickctl(t, "stock", testdata("stock.csv"))
	if code != 0 {
		t.Fatalf("exit %d", code)
	}
	want := "A01-03-1 TENT-2P 6\nA02-11-1 HEADLAMP 15\nA02-11-1 MUG-TI 9\nA02-07-2 STOVE-MINI 2\n" +
		"A03-02-3 PAD-XL 4\nA03-14-1 BAG-0C 3\nA04-05-2 POLES-CF 10\n"
	if out != want {
		t.Errorf("got\n%s\nwant\n%s", out, want)
	}
}

func TestCheckOK(t *testing.T) {
	code, out, _ := pickctl(t, "check", testdata("orders.csv"), testdata("stock.csv"))
	if code != 0 || out != "ok: 4 orders, 9 lines, 14 units\n" {
		t.Errorf("exit %d, output %q", code, out)
	}
}

func TestCheckUnknownSKU(t *testing.T) {
	dir := t.TempDir()
	orders := filepath.Join(dir, "orders.csv")
	data := "order_id,placed_at,sku,qty\nK-1,2026-09-30T20:00:00Z,TENT-2P,1\nK-1,2026-09-30T20:00:00Z,KAYAK,1\n"
	if err := os.WriteFile(orders, []byte(data), 0o644); err != nil {
		t.Fatal(err)
	}
	code, out, _ := pickctl(t, "check", orders, testdata("stock.csv"))
	if code != 1 || out != "order K-1 line 2: unknown sku KAYAK\n1 problems\n" {
		t.Errorf("exit %d, output %q", code, out)
	}
}

func TestUsage(t *testing.T) {
	for _, args := range [][]string{nil, {"stock"}, {"check", "a.csv"}, {"ship"}} {
		code, out, errs := pickctl(t, args...)
		if code != 2 || out != "" || !strings.HasPrefix(errs, "usage:") {
			t.Errorf("%v: exit %d, stdout %q, stderr %q", args, code, out, errs)
		}
	}
}

func TestMissingFile(t *testing.T) {
	code, _, errs := pickctl(t, "stock", filepath.Join(t.TempDir(), "none.csv"))
	if code != 1 || !strings.HasPrefix(errs, "pickctl: ") {
		t.Errorf("exit %d, stderr %q", code, errs)
	}
}
