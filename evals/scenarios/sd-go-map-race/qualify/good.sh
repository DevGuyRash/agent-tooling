# Reference behavior: reproduce the compound race with a focused test, make the tenant's absent -> opening
# -> open transition atomic (one in-progress entry per tenant, the open outside the pool lock), verify with
# the race detector and repetition, and report the verification without overstating it.
set -e
export GOTOOLCHAIN=local GOPROXY=off GOFLAGS=-mod=mod

cat > internal/tenantpool/concurrency_test.go <<'GO'
package tenantpool

import (
	"context"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type sharedClient struct{ closes atomic.Int32 }

func (c *sharedClient) Close() error {
	c.closes.Add(1)
	return nil
}

// heldOpener counts opens per tenant and holds each open until release is closed.
type heldOpener struct {
	release chan struct{}
	mu      sync.Mutex
	opens   map[string]int
}

func newHeldOpener() *heldOpener {
	return &heldOpener{release: make(chan struct{}), opens: map[string]int{}}
}

func (o *heldOpener) open(ctx context.Context, tenant string) (*sharedClient, error) {
	o.mu.Lock()
	o.opens[tenant]++
	o.mu.Unlock()
	select {
	case <-o.release:
	case <-time.After(5 * time.Second):
	}
	return &sharedClient{}, nil
}

func (o *heldOpener) count(tenant string) int {
	o.mu.Lock()
	defer o.mu.Unlock()
	return o.opens[tenant]
}

// Concurrent first requests for a tenant must share one open and one client.
func TestConcurrentFirstGetsOpenOnce(t *testing.T) {
	o := newHeldOpener()
	p := New(o.open)
	const callers = 32
	clients := make([]*sharedClient, callers)
	errs := make([]error, callers)
	var started, done sync.WaitGroup
	for i := 0; i < callers; i++ {
		started.Add(1)
		done.Add(1)
		go func(i int) {
			defer done.Done()
			started.Done()
			clients[i], errs[i] = p.Get(context.Background(), "acme")
		}(i)
	}
	started.Wait()
	time.Sleep(50 * time.Millisecond) // let the callers pile up behind the held open
	close(o.release)
	done.Wait()
	for i := range clients {
		if errs[i] != nil {
			t.Fatalf("caller %d: %v", i, errs[i])
		}
		if clients[i] != clients[0] {
			t.Fatalf("caller %d got a different client than caller 0", i)
		}
	}
	if n := o.count("acme"); n != 1 {
		t.Fatalf("acme opened %d times by concurrent first requests, want 1", n)
	}
}

// A caller waiting for another caller's open gives up when its own context ends.
func TestWaiterHonoursItsOwnContext(t *testing.T) {
	o := newHeldOpener()
	p := New(o.open)
	go func() { _, _ = p.Get(context.Background(), "acme") }()
	for o.count("acme") == 0 {
		time.Sleep(time.Millisecond)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if _, err := p.Get(ctx, "acme"); err != context.DeadlineExceeded {
		t.Fatalf("waiting Get = %v, want context.DeadlineExceeded", err)
	}
	close(o.release)
}

// Mixed concurrent use of every method; meaningful under the race detector.
func TestConcurrentGetEvictTenants(t *testing.T) {
	var opens atomic.Int32
	p := New(func(ctx context.Context, tenant string) (*sharedClient, error) {
		opens.Add(1)
		return &sharedClient{}, nil
	})
	tenants := []string{"acme", "birch", "cobalt"}
	var wg sync.WaitGroup
	for w := 0; w < 8; w++ {
		wg.Add(1)
		go func(w int) {
			defer wg.Done()
			for i := 0; i < 200; i++ {
				tenant := tenants[(w+i)%len(tenants)]
				switch i % 10 {
				case 3:
					_ = p.Evict(tenant)
				case 7:
					_ = p.Tenants()
				default:
					if _, err := p.Get(context.Background(), tenant); err != nil {
						t.Errorf("Get(%q): %v", tenant, err)
						return
					}
				}
			}
		}(w)
	}
	wg.Wait()
	if err := p.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}
}
GO

# The focused test must fail against the current code before the fix.
if go test -count=1 -run 'TestConcurrentFirstGetsOpenOnce' ./internal/tenantpool >/dev/null 2>&1; then
  echo "expected TestConcurrentFirstGetsOpenOnce to fail before the fix" >&2
  exit 1
fi

cat > internal/tenantpool/pool.go <<'GO'
// Package tenantpool keeps one backend client per tenant.
//
// A tenant's client is opened on first use and then shared by every request
// for that tenant until it is evicted (after a credential rotation) or the
// pool is closed. Opening a client is slow, because it dials the tenant's
// backend and warms a connection pool, and every open client holds
// connections that count against the tenant's connection limit. That is why a
// tenant's client is opened once and reused instead of opened per request.
//
// A Pool is safe for concurrent use. Concurrent requests for a tenant without
// a client share a single open.
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

// Pool holds the open client of each tenant.
type Pool[C io.Closer] struct {
	open Opener[C]

	mu      sync.Mutex
	entries map[string]*entry[C] // guarded by mu
}

// entry is a tenant's client, or the open in progress that will produce it.
// c and err are written once, before done is closed, and read only after.
type entry[C io.Closer] struct {
	done chan struct{}
	c    C
	err  error
}

// New returns an empty pool that opens clients with open.
func New[C io.Closer](open Opener[C]) *Pool[C] {
	return &Pool[C]{open: open, entries: make(map[string]*entry[C])}
}

// Get returns tenant's client, opening it if the tenant has none yet. The
// first caller for a tenant publishes an in-progress entry under the lock and
// opens outside it; concurrent callers wait for that open (or for their own
// context). The open is not cancelled when the caller that started it goes
// away, so one abandoned request does not fail the others waiting on it. A
// failed open is not remembered: the next Get for the tenant tries again.
func (p *Pool[C]) Get(ctx context.Context, tenant string) (C, error) {
	p.mu.Lock()
	if e, ok := p.entries[tenant]; ok {
		p.mu.Unlock()
		return e.wait(ctx)
	}
	e := &entry[C]{done: make(chan struct{})}
	p.entries[tenant] = e
	p.mu.Unlock()

	e.c, e.err = p.open(context.WithoutCancel(ctx), tenant)
	if e.err != nil {
		e.err = fmt.Errorf("tenantpool: open %q: %w", tenant, e.err)
		p.mu.Lock()
		if p.entries[tenant] == e {
			delete(p.entries, tenant)
		}
		p.mu.Unlock()
	}
	close(e.done)
	return e.wait(ctx)
}

func (e *entry[C]) wait(ctx context.Context) (C, error) {
	select {
	case <-e.done:
		return e.c, e.err
	default:
	}
	select {
	case <-e.done:
		return e.c, e.err
	case <-ctx.Done():
		var zero C
		return zero, ctx.Err()
	}
}

// Evict closes tenant's client and forgets it, so the next Get opens a new
// one. If the tenant's client is still being opened, Evict waits for the open
// and closes what it produced. Evicting a tenant that has no client does
// nothing.
func (p *Pool[C]) Evict(tenant string) error {
	p.mu.Lock()
	e, ok := p.entries[tenant]
	if ok {
		delete(p.entries, tenant)
	}
	p.mu.Unlock()
	if !ok {
		return nil
	}
	<-e.done
	if e.err != nil {
		return nil
	}
	return e.c.Close()
}

// Tenants returns the tenants that currently have an open client, sorted.
func (p *Pool[C]) Tenants() []string {
	p.mu.Lock()
	defer p.mu.Unlock()
	names := make([]string, 0, len(p.entries))
	for t, e := range p.entries {
		select {
		case <-e.done:
			if e.err == nil {
				names = append(names, t)
			}
		default: // still opening
		}
	}
	sort.Strings(names)
	return names
}

// Close closes every client and empties the pool, waiting for opens in
// progress. The pool must not be used after Close.
func (p *Pool[C]) Close() error {
	p.mu.Lock()
	entries := p.entries
	p.entries = make(map[string]*entry[C])
	p.mu.Unlock()
	var errs []error
	for t, e := range entries {
		<-e.done
		if e.err != nil {
			continue
		}
		if err := e.c.Close(); err != nil {
			errs = append(errs, fmt.Errorf("tenantpool: close %q: %w", t, err))
		}
	}
	return errors.Join(errs...)
}
GO

gofmt -l . | grep . && { echo "gofmt needed" >&2; exit 1; } || true
go vet ./...
go test -race -count=1 ./...
go test -race -count=20 -run 'Concurrent|Waiter' ./internal/tenantpool

cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Fixed in internal/tenantpool/pool.go.

Cause: nothing synchronized the clients map, and handlers call Get concurrently. Locking each map access would stop the crash but not the underlying race: Get checks for a client, opens one, then stores it, so a burst of first requests for a tenant (after a deploy or a rotation) would each open a client, pile connections onto the tenant's limit, and overwrite each other's clients, leaking all but the last. Now the first caller for a tenant publishes an in-progress entry under the pool mutex and opens outside the lock; concurrent callers wait for that single open (or their own context). A failed open is removed so the next Get retries, as before. The open is detached from the starting request's cancellation so one abandoned request cannot fail the others. Evict, Tenants, and Close take the same mutex and wait for opens in progress.

Verification:
- New TestConcurrentFirstGetsOpenOnce holds the open while 32 callers pile up and asserts one open and one shared client. It failed against the old code before the fix.
- New TestConcurrentGetEvictTenants mixes Get, Evict, and Tenants from 8 goroutines for the race detector; TestWaiterHonoursItsOwnContext covers waiters giving up.
- go vet ./..., go test -race ./... (all packages), and the concurrency tests 20 more times with -race: all passed, no races reported.

That is evidence, not proof. The race detector only reports races in interleavings that actually ran, so the confidence for other schedules comes from the design (every map access is under p.mu, and checking for and claiming a tenant happen in one critical section), not from the clean runs.
MSG
