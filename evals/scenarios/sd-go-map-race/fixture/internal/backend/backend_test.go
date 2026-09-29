package backend

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func newBackend(t *testing.T, healthy bool) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("GET /acme/healthz", func(w http.ResponseWriter, r *http.Request) {
		if !healthy {
			http.Error(w, "down for maintenance", http.StatusServiceUnavailable)
		}
	})
	mux.HandleFunc("GET /acme/invoices", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`[{"id":"inv_1","amount_cents":1250,"status":"paid"}]`))
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

func TestOpenAndListInvoices(t *testing.T) {
	srv := newBackend(t, true)
	d := &Dialer{URLTemplate: srv.URL + "/{tenant}"}

	c, err := d.Open(context.Background(), "acme")
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer c.Close()

	invs, err := c.Invoices(context.Background())
	if err != nil {
		t.Fatalf("Invoices: %v", err)
	}
	if len(invs) != 1 || invs[0].ID != "inv_1" || invs[0].AmountCents != 1250 {
		t.Fatalf("Invoices = %+v", invs)
	}
}

func TestOpenFailsWhenBackendUnhealthy(t *testing.T) {
	srv := newBackend(t, false)
	d := &Dialer{URLTemplate: srv.URL + "/{tenant}"}

	if c, err := d.Open(context.Background(), "acme"); err == nil {
		c.Close()
		t.Fatal("Open succeeded against an unhealthy backend")
	}
}
