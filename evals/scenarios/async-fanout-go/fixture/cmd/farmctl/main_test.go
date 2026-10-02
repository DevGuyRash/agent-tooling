package main

import (
	"bytes"
	"strings"
	"testing"

	"hollowcreek.example/farmctl/internal/fakegw"
	"hollowcreek.example/farmctl/internal/gateway"
)

func runFarmctl(t *testing.T, env map[string]string, args ...string) (int, string, string) {
	t.Helper()
	var out, errb bytes.Buffer
	code := run(args, &out, &errb, func(k string) string { return env[k] })
	return code, out.String(), errb.String()
}

func TestListSorted(t *testing.T) {
	gw := fakegw.Start(t, fakegw.Config{Readings: []gateway.Reading{{Name: "INV-010"}, {Name: "INV-002"}}})
	code, out, _ := runFarmctl(t, nil, "-gateway", gw.Addr, "list")
	if code != 0 || out != "INV-002\nINV-010\n" {
		t.Fatalf("list: exit %d, output %q", code, out)
	}
}

func TestRead(t *testing.T) {
	gw := fakegw.Start(t, fakegw.Config{Readings: []gateway.Reading{
		{Name: "INV-001", WhToday: 4821, WattsNow: 1520}, {Name: "INV-002", WhToday: 0, WattsNow: 0}}})
	code, out, _ := runFarmctl(t, nil, "-gateway", gw.Addr, "read", "INV-002", "INV-001")
	want := "INV-002: 0 Wh today, 0 W now\nINV-001: 4821 Wh today, 1520 W now\n"
	if code != 0 || out != want {
		t.Fatalf("read: exit %d, output %q, want %q", code, out, want)
	}
}

func TestReadUsesEnvironment(t *testing.T) {
	gw := fakegw.Start(t, fakegw.Config{Readings: []gateway.Reading{{Name: "INV-001", WhToday: 7, WattsNow: 3}}})
	code, out, _ := runFarmctl(t, map[string]string{"FARMCTL_GATEWAY": gw.Addr}, "read", "INV-001")
	if code != 0 || out != "INV-001: 7 Wh today, 3 W now\n" {
		t.Fatalf("read: exit %d, output %q", code, out)
	}
}

func TestReadError(t *testing.T) {
	gw := fakegw.Start(t, fakegw.Config{Errors: map[string]string{"INV-003": "503 inverter fault"}})
	code, out, errOut := runFarmctl(t, nil, "-gateway", gw.Addr, "read", "INV-003")
	if code != 1 || out != "" || !strings.Contains(errOut, "error 503 inverter fault") {
		t.Fatalf("read: exit %d, output %q, stderr %q", code, out, errOut)
	}
}

func TestUsage(t *testing.T) {
	for _, args := range [][]string{{}, {"frobnicate"}, {"read"}, {"list", "extra"}} {
		if code, _, _ := runFarmctl(t, nil, args...); code != 2 {
			t.Errorf("%q: exit %d, want 2", args, code)
		}
	}
}
