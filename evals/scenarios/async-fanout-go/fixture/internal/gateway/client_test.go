package gateway_test

import (
	"errors"
	"net"
	"testing"

	"hollowcreek.example/farmctl/internal/fakegw"
	"hollowcreek.example/farmctl/internal/gateway"
)

func TestInverters(t *testing.T) {
	gw := fakegw.Start(t, fakegw.Config{Readings: []gateway.Reading{{Name: "INV-002"}, {Name: "INV-001"}},
		Offline: []string{"INV-003"}})
	names, err := (&gateway.Client{Addr: gw.Addr}).Inverters()
	if err != nil {
		t.Fatal(err)
	}
	if len(names) != 3 || names[0] != "INV-002" || names[2] != "INV-003" {
		t.Fatalf("names = %q, want the bus order", names)
	}
}

func TestRead(t *testing.T) {
	gw := fakegw.Start(t, fakegw.Config{Readings: []gateway.Reading{{Name: "INV-001", WhToday: 4821, WattsNow: 1520}}})
	r, err := (&gateway.Client{Addr: gw.Addr}).Read("INV-001")
	if err != nil {
		t.Fatal(err)
	}
	if r != (gateway.Reading{Name: "INV-001", WhToday: 4821, WattsNow: 1520}) {
		t.Fatalf("reading = %+v", r)
	}
	if got := r.String(); got != "INV-001: 4821 Wh today, 1520 W now" {
		t.Fatalf("String() = %q", got)
	}
}

func TestReadGatewayError(t *testing.T) {
	gw := fakegw.Start(t, fakegw.Config{Errors: map[string]string{"INV-003": "503 inverter fault"}})
	_, err := (&gateway.Client{Addr: gw.Addr}).Read("INV-003")
	var gerr *gateway.Error
	if !errors.As(err, &gerr) || gerr.Code != 503 || gerr.Text != "inverter fault" {
		t.Fatalf("err = %v, want ERR 503 inverter fault", err)
	}
}

func TestReadUnknown(t *testing.T) {
	gw := fakegw.Start(t, fakegw.Config{})
	_, err := (&gateway.Client{Addr: gw.Addr}).Read("INV-999")
	var gerr *gateway.Error
	if !errors.As(err, &gerr) || gerr.Code != 404 {
		t.Fatalf("err = %v, want ERR 404", err)
	}
}

func TestUnreachable(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	addr := ln.Addr().String()
	ln.Close()
	if _, err := (&gateway.Client{Addr: addr}).Inverters(); err == nil {
		t.Fatal("no error from a gateway that is not there")
	}
}
