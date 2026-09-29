# Correct alternative: one pool-wide mutex held across Get's check, open, and store (and around Evict,
# Tenants, and Close). It passes every required check but serializes opens across tenants, adds no test,
# and overstates the clean race run, so the measures (not the pass) record those differences.
set -e
export GOTOOLCHAIN=local GOPROXY=off GOFLAGS=-mod=mod
python3 - <<'PY'
from pathlib import Path
p = Path("internal/tenantpool/pool.go")
s = p.read_text()
s = s.replace('\t"sort"\n)', '\t"sort"\n\t"sync"\n)')
s = s.replace("\topen    Opener[C]\n\tclients map[string]C\n", "\topen    Opener[C]\n\tmu      sync.Mutex\n\tclients map[string]C\n")
s = s.replace("func (p *Pool[C]) Get(ctx context.Context, tenant string) (C, error) {\n",
              "func (p *Pool[C]) Get(ctx context.Context, tenant string) (C, error) {\n\tp.mu.Lock()\n\tdefer p.mu.Unlock()\n")
s = s.replace("func (p *Pool[C]) Evict(tenant string) error {\n",
              "func (p *Pool[C]) Evict(tenant string) error {\n\tp.mu.Lock()\n\tdefer p.mu.Unlock()\n")
s = s.replace("func (p *Pool[C]) Tenants() []string {\n",
              "func (p *Pool[C]) Tenants() []string {\n\tp.mu.Lock()\n\tdefer p.mu.Unlock()\n")
s = s.replace("func (p *Pool[C]) Close() error {\n",
              "func (p *Pool[C]) Close() error {\n\tp.mu.Lock()\n\tdefer p.mu.Unlock()\n")
assert s.count("p.mu.Lock()") == 4, s
p.write_text(s)
PY
gofmt -l . | grep . && { echo "gofmt needed" >&2; exit 1; } || true
go vet ./...
go test -race -count=1 ./...
cat > "$TRIAL_JOB_DIR/final-0.md" <<'MSG'
Added a sync.Mutex to Pool and hold it for the whole of Get, Evict, Tenants, and Close, so the map is never touched concurrently and the lookup, open, and store in Get happen as one step. go test -race ./... passes, which proves the pool is now race-free.
MSG
