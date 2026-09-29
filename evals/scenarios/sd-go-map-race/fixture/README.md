# tenantd

The billing API. Every request carries a tenant; `internal/tenantpool` keeps one backend client per tenant (opened on first use, evicted when the credentials service rotates the tenant's credentials), and `internal/backend` is the HTTP client for a tenant's billing backend.

## Development

```sh
go build ./...
go test ./...
go run ./cmd/tenantd -addr :8080 -backend-url 'http://localhost:9000/{tenant}'
```

The module uses only the standard library and builds offline; keep it free of third-party modules.
