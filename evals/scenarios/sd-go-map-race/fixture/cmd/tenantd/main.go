// Command tenantd serves the billing API for every tenant.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"acme.example/tenantd/internal/backend"
	"acme.example/tenantd/internal/tenantpool"
)

func main() {
	addr := flag.String("addr", ":8080", "listen address")
	backendURL := flag.String("backend-url", "https://{tenant}.billing.internal", "tenant backend base URL; {tenant} is replaced by the tenant name")
	flag.Parse()

	dialer := &backend.Dialer{URLTemplate: *backendURL}
	srv := &server{pool: tenantpool.New(dialer.Open)}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/{tenant}/invoices", srv.invoices)
	mux.HandleFunc("POST /admin/{tenant}/rotate", srv.rotate)
	mux.HandleFunc("GET /debug/tenants", srv.tenants)
	httpSrv := &http.Server{Addr: *addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	shutdown := make(chan struct{})
	go func() {
		defer close(shutdown)
		<-ctx.Done()
		sctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
		defer cancel()
		if err := httpSrv.Shutdown(sctx); err != nil {
			log.Printf("shutdown: %v", err)
		}
	}()

	log.Printf("tenantd listening on %s", *addr)
	if err := httpSrv.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
	<-shutdown // handlers have returned; nothing uses the pool any more
	if err := srv.pool.Close(); err != nil {
		log.Printf("closing tenant clients: %v", err)
	}
}

type server struct {
	pool *tenantpool.Pool[*backend.Client]
}

func (s *server) invoices(w http.ResponseWriter, r *http.Request) {
	c, err := s.pool.Get(r.Context(), r.PathValue("tenant"))
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	invs, err := c.Invoices(r.Context())
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	writeJSON(w, invs)
}

// rotate is called by the credentials service after it rotates a tenant's
// backend credentials, so that the next request opens a client with the new
// credentials.
func (s *server) rotate(w http.ResponseWriter, r *http.Request) {
	tenant := r.PathValue("tenant")
	if err := s.pool.Evict(tenant); err != nil {
		log.Printf("rotate %s: closing old client: %v", tenant, err)
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *server) tenants(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, s.pool.Tenants())
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("writing response: %v", err)
	}
}
