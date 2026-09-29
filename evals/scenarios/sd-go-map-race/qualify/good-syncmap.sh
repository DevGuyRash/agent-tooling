# Correct alternative: sync.Map of per-tenant in-progress entries; LoadOrStore elects the one caller that
# opens, CompareAndDelete drops a failed open so the next Get retries. Adds a concurrency test and
# reports the verification with its limits.
set -e
export GOTOOLCHAIN=local GOPROXY=off GOFLAGS=-mod=mod
cat > internal/tenantpool/pool.go <<'GO'
// Package tenantpool keeps one backend client per tenant.
//
// A tenant's client is opened on first use and then shared by every request
// for that tenant until it is evicted (after a credential rotation) or the
// pool is closed. Opening a client is slow, because it dials the tenant's
// backend and warms a connection pool, and every open client holds
// connections that count against the tenant's connection limit. That is why a
// tenant's client is opened once and reused instead of opened per request.
package tenantpool

import (
	"context"
	"errors"
	"fmt"
	"io"
	"sort"
	"sync"
)

// Opener opens a new client for tenant.
type Opener[C io.Closer] func(ctx context.Context, tenant string) (C, error)

// Pool holds the open client of each tenant. It is safe for concurrent use.
type Pool[C io.Closer] struct {
	open    Opener[C]
	entries sync.Map // tenant -> *entry[C]
}

// entry is a tenant's client or the open that will produce it; c and err are
// set before ready is closed.
type entry[C io.Closer] struct {
	ready chan struct{}
	c     C
	err   error
}

// New returns an empty pool that opens clients with open.
func New[C io.Closer](open Opener[C]) *Pool[C] {
	return &Pool[C]{open: open}
}

// Get returns tenant's client, opening it if the tenant has none yet. Only
// one caller opens a tenant's client; concurrent callers wait for its result.
// A failed open is not remembered: the next Get for the tenant tries again.
func (p *Pool[C]) Get(ctx context.Context, tenant string) (C, error) {
	if v, ok := p.entries.Load(tenant); ok {
		return v.(*entry[C]).wait(ctx)
	}
	e := &entry[C]{ready: make(chan struct{})}
	if v, loaded := p.entries.LoadOrStore(tenant, e); loaded {
		return v.(*entry[C]).wait(ctx)
	}
	e.c, e.err = p.open(ctx, tenant)
	if e.err != nil {
		e.err = fmt.Errorf("tenantpool: open %q: %w", tenant, e.err)
		p.entries.CompareAndDelete(tenant, e)
	}
	close(e.ready)
	return e.c, e.err
}

func (e *entry[C]) wait(ctx context.Context) (C, error) {
	select {
	case <-e.ready:
		return e.c, e.err
	case <-ctx.Done():
		var zero C
		return zero, ctx.Err()
	}
}

// Evict closes tenant's client and forgets it, so the next Get opens a new
// one; an open in progress is waited for and its client closed. Evicting a
// tenant that has no client does nothing.
func (p *Pool[C]) Evict(tenant string) error {
	v, ok := p.entries.LoadAndDelete(tenant)
	if !ok {
		return nil
	}
	e := v.(*entry[C])
	<-e.ready
	if e.err != nil {
		return nil
	}
	return e.c.Close()
}

// Tenants returns the tenants that currently have an open client, sorted.
func (p *Pool[C]) Tenants() []string {
	var names []string
	p.entries.Range(func(k, v any) bool {
		e := v.(*entry[C])
		select {
		case <-e.ready:
			if e.err == nil {
				names = append(names, k.(string))
			}
		default:
		}
		return true
	})
	sort.Strings(names)
	if names == nil {
		names = []string{}
	}
	return names
}

// Close closes every client and empties the pool. The pool must not be used
// after Close.
func (p *Pool[C]) Close() error {
	var errs []error
	p.entries.Range(func(k, v any) bool {
		p.entries.Delete(k)
		e := v.(*entry[C])
		<-e.ready
		if e.err == nil {
			if err := e.c.Close(); err != nil {
				errs = append(errs, fmt.Errorf("tenantpool: close %q: %w", k, err))
			}
		}
		return true
	})
	return errors.Join(errs...)
}
GO
cat > internal/tenantpool/burst_test.go <<'GO'
package tenantpool

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
)

type burstClient struct{ id int32 }

func (*burstClient) Close() error { return nil }

func TestBurstOfFirstRequestsSharesOneClient(t *testing.T) {
	var opens atomic.Int32
	p := New(func(ctx context.Context, tenant string) (*burstClient, error) {
		return &burstClient{id: opens.Add(1)}, nil
	})
	got := make([]*burstClient, 64)
	var wg sync.WaitGroup
	for i := range got {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			c, err := p.Get(context.Background(), "acme")
			if err != nil {
				t.Errorf("Get: %v", err)
			}
			got[i] = c
		}(i)
	}
	wg.Wait()
	for i, c := range got {
		if c != got[0] {
			t.Fatalf("request %d got client %d, request 0 got client %d", i, c.id, got[0].id)
		}
	}
	if n := opens.Load(); n != 1 {
		t.Fatalf("opened %d clients for one tenant, want 1", n)
	}
}
GO
gofmt -l . | grep . && { echo "gofmt needed" >&2; exit 1; } || true
go vet ./...
go test -race -count=1 ./...
go test -race -count=10 -run Burst ./internal/tenantpool
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
The pool now keeps a sync.Map of per-tenant entries. The first request for a tenant stores an in-progress entry with LoadOrStore and opens the client; every concurrent request for that tenant waits on the same entry, so a burst after a deploy or rotation opens one client instead of one per request (the old code would also have overwritten and leaked the extras). A failed open is deleted so the next request retries. Evict, Tenants, and Close go through the same map.

Verification: added TestBurstOfFirstRequestsSharesOneClient (64 concurrent first requests share one client and one open); ran go vet, go test -race ./..., and that test 10 times under -race, all clean. The race detector can only report races in the interleavings those runs happened to execute, so treat this as strong evidence rather than a proof; the argument for other schedules is that every access to the map goes through sync.Map and every entry field is published before its ready channel closes.
MSG
