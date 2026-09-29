# Partial: the pool fix is correct (one mutex across check, open, and store), but the new concurrency test
# appends to a shared slice from many goroutines, and the tests were never run with -race, so the
# repository's own suite fails under the race detector.
set -e
export GOTOOLCHAIN=local GOPROXY=off GOFLAGS=-mod=mod
python3 - <<'PY'
from pathlib import Path
p = Path("internal/tenantpool/pool.go")
s = p.read_text()
s = s.replace('\t"sort"\n)', '\t"sort"\n\t"sync"\n)')
s = s.replace("\topen    Opener[C]\n\tclients map[string]C\n", "\topen    Opener[C]\n\tmu      sync.Mutex\n\tclients map[string]C\n")
for sig in ("func (p *Pool[C]) Get(ctx context.Context, tenant string) (C, error) {\n",
            "func (p *Pool[C]) Evict(tenant string) error {\n",
            "func (p *Pool[C]) Tenants() []string {\n",
            "func (p *Pool[C]) Close() error {\n"):
    s = s.replace(sig, sig + "\tp.mu.Lock()\n\tdefer p.mu.Unlock()\n")
assert s.count("p.mu.Lock()") == 4, s
p.write_text(s)
PY
cat > internal/tenantpool/burst_test.go <<'GO'
package tenantpool

import (
	"context"
	"sync"
	"testing"
)

func TestBurstSharesOneClient(t *testing.T) {
	var mu sync.Mutex
	opens := 0
	p := New(func(ctx context.Context, tenant string) (*fakeClient, error) {
		mu.Lock()
		opens++
		mu.Unlock()
		return &fakeClient{tenant: tenant}, nil
	})
	var got []*fakeClient
	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			c, err := p.Get(context.Background(), "acme")
			if err != nil {
				t.Errorf("Get: %v", err)
				return
			}
			got = append(got, c)
		}()
	}
	wg.Wait()
	for _, c := range got {
		if c != got[0] {
			t.Fatalf("callers received different clients")
		}
	}
	if opens != 1 {
		t.Fatalf("opened %d times, want 1", opens)
	}
}
GO
gofmt -l . | grep . && { echo "gofmt needed" >&2; exit 1; } || true
go vet ./...
go test -count=1 ./...
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Pool now has a mutex held across Get's lookup, open, and store (and around Evict, Tenants, and Close), so a burst of first requests opens a tenant's client once and the map is never touched concurrently. Added TestBurstSharesOneClient (32 concurrent first requests share one client, one open). go test ./... passes.
MSG
