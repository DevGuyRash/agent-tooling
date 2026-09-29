// Package backend is the HTTP client for a tenant's billing backend.
package backend

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Dialer opens clients for tenant backends.
type Dialer struct {
	// URLTemplate is the backend base URL with {tenant} in place of the
	// tenant name, for example "https://{tenant}.billing.internal".
	URLTemplate string
}

// Client talks to one tenant's backend. Each client keeps its own pool of
// keep-alive connections to that backend.
type Client struct {
	base string
	http *http.Client
}

// Open creates a client for tenant and checks that its backend answers. It
// dials the backend and leaves the connection in the client's pool.
func (d *Dialer) Open(ctx context.Context, tenant string) (*Client, error) {
	c := &Client{
		base: strings.TrimRight(strings.ReplaceAll(d.URLTemplate, "{tenant}", tenant), "/"),
		http: &http.Client{
			Transport: &http.Transport{MaxIdleConnsPerHost: 8, IdleConnTimeout: 90 * time.Second},
			Timeout:   10 * time.Second,
		},
	}
	if err := c.ping(ctx); err != nil {
		c.Close()
		return nil, err
	}
	return c, nil
}

func (c *Client) ping(ctx context.Context) error {
	resp, err := c.get(ctx, "/healthz")
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("backend: %s/healthz: %s", c.base, resp.Status)
	}
	return nil
}

// Invoice is one invoice as the backend reports it.
type Invoice struct {
	ID          string `json:"id"`
	AmountCents int64  `json:"amount_cents"`
	Status      string `json:"status"`
}

// Invoices lists the tenant's invoices.
func (c *Client) Invoices(ctx context.Context) ([]Invoice, error) {
	resp, err := c.get(ctx, "/invoices")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("backend: %s/invoices: %s", c.base, resp.Status)
	}
	var out []Invoice
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("backend: decoding invoices: %w", err)
	}
	return out, nil
}

func (c *Client) get(ctx context.Context, path string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.base+path, nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("backend: %w", err)
	}
	return resp, nil
}

// Close releases the client's idle connections.
func (c *Client) Close() error {
	c.http.CloseIdleConnections()
	return nil
}
