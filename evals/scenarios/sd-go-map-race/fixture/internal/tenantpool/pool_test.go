package tenantpool

import (
	"context"
	"errors"
	"slices"
	"testing"
)

type fakeClient struct {
	tenant string
	closed int
}

func (c *fakeClient) Close() error {
	c.closed++
	return nil
}

// fakeOpener hands out a new fakeClient per open and counts opens per tenant.
type fakeOpener struct {
	opens map[string]int
	fail  map[string]error
}

func newFakeOpener() *fakeOpener {
	return &fakeOpener{opens: map[string]int{}, fail: map[string]error{}}
}

func (o *fakeOpener) open(_ context.Context, tenant string) (*fakeClient, error) {
	o.opens[tenant]++
	if err := o.fail[tenant]; err != nil {
		return nil, err
	}
	return &fakeClient{tenant: tenant}, nil
}

func TestGetOpensOnceAndReuses(t *testing.T) {
	o := newFakeOpener()
	p := New(o.open)
	ctx := context.Background()

	first, err := p.Get(ctx, "acme")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	second, err := p.Get(ctx, "acme")
	if err != nil {
		t.Fatalf("second Get: %v", err)
	}
	if first != second {
		t.Fatalf("second Get returned a different client")
	}
	if first.tenant != "acme" {
		t.Fatalf("client tenant = %q, want acme", first.tenant)
	}
	if o.opens["acme"] != 1 {
		t.Fatalf("opened %d times, want 1", o.opens["acme"])
	}
}

func TestGetReturnsOpenErrorAndRetries(t *testing.T) {
	o := newFakeOpener()
	p := New(o.open)
	ctx := context.Background()
	boom := errors.New("backend unavailable")
	o.fail["acme"] = boom

	if _, err := p.Get(ctx, "acme"); !errors.Is(err, boom) {
		t.Fatalf("Get error = %v, want %v", err, boom)
	}
	if got := p.Tenants(); len(got) != 0 {
		t.Fatalf("Tenants after failed open = %v, want none", got)
	}

	delete(o.fail, "acme")
	c, err := p.Get(ctx, "acme")
	if err != nil {
		t.Fatalf("Get after the backend recovered: %v", err)
	}
	if c == nil || o.opens["acme"] != 2 {
		t.Fatalf("client = %v after %d opens, want a client after 2 opens", c, o.opens["acme"])
	}
}

func TestEvictClosesClientAndNextGetReopens(t *testing.T) {
	o := newFakeOpener()
	p := New(o.open)
	ctx := context.Background()

	old, err := p.Get(ctx, "acme")
	if err != nil {
		t.Fatalf("Get: %v", err)
	}
	if err := p.Evict("acme"); err != nil {
		t.Fatalf("Evict: %v", err)
	}
	if old.closed != 1 {
		t.Fatalf("evicted client closed %d times, want 1", old.closed)
	}
	if got := p.Tenants(); len(got) != 0 {
		t.Fatalf("Tenants after Evict = %v, want none", got)
	}

	fresh, err := p.Get(ctx, "acme")
	if err != nil {
		t.Fatalf("Get after Evict: %v", err)
	}
	if fresh == old || o.opens["acme"] != 2 {
		t.Fatalf("Get after Evict reused the old client or did not reopen (opens = %d)", o.opens["acme"])
	}
	if err := p.Evict("nobody"); err != nil {
		t.Fatalf("Evict of an unknown tenant: %v", err)
	}
}

func TestTenantsSorted(t *testing.T) {
	o := newFakeOpener()
	p := New(o.open)
	ctx := context.Background()
	for _, tenant := range []string{"cobalt", "acme", "birch"} {
		if _, err := p.Get(ctx, tenant); err != nil {
			t.Fatalf("Get(%q): %v", tenant, err)
		}
	}
	if got, want := p.Tenants(), []string{"acme", "birch", "cobalt"}; !slices.Equal(got, want) {
		t.Fatalf("Tenants = %v, want %v", got, want)
	}
}

func TestCloseClosesEveryClient(t *testing.T) {
	o := newFakeOpener()
	p := New(o.open)
	ctx := context.Background()
	a, _ := p.Get(ctx, "acme")
	b, _ := p.Get(ctx, "birch")

	if err := p.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}
	if a.closed != 1 || b.closed != 1 {
		t.Fatalf("Close closed clients %d and %d times, want 1 each", a.closed, b.closed)
	}
}
