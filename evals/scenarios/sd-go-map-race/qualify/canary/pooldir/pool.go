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
)

// Opener opens a new client for tenant.
type Opener[C io.Closer] func(ctx context.Context, tenant string) (C, error)

// Pool holds the open client of each tenant.
type Pool[C io.Closer] struct {
	open    Opener[C]
	clients map[string]C
}

// New returns an empty pool that opens clients with open.
func New[C io.Closer](open Opener[C]) *Pool[C] {
	return &Pool[C]{open: open, clients: make(map[string]C)}
}

// Get returns tenant's client, opening it if the tenant has none yet. A failed
// open is not remembered: the next Get for the tenant tries again.
func (p *Pool[C]) Get(ctx context.Context, tenant string) (C, error) {
	if c, ok := p.clients[tenant]; ok {
		return c, nil
	}
	c, err := p.open(ctx, tenant)
	if err != nil {
		var zero C
		return zero, fmt.Errorf("tenantpool: open %q: %w", tenant, err)
	}
	p.clients[tenant] = c
	return c, nil
}

// Evict closes tenant's client and forgets it, so the next Get opens a new
// one. Evicting a tenant that has no client does nothing.
func (p *Pool[C]) Evict(tenant string) error {
	c, ok := p.clients[tenant]
	if !ok {
		return nil
	}
	delete(p.clients, tenant)
	return c.Close()
}

// Tenants returns the tenants that currently have an open client, sorted.
func (p *Pool[C]) Tenants() []string {
	names := make([]string, 0, len(p.clients))
	for t := range p.clients {
		names = append(names, t)
	}
	sort.Strings(names)
	return names
}

// Close closes every client and empties the pool. The pool must not be used
// after Close.
func (p *Pool[C]) Close() error {
	var errs []error
	for t, c := range p.clients {
		if err := c.Close(); err != nil {
			errs = append(errs, fmt.Errorf("tenantpool: close %q: %w", t, err))
		}
	}
	clear(p.clients)
	return errors.Join(errs...)
}
