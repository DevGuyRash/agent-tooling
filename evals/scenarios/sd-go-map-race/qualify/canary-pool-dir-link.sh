# Check-safety probe: the pool's package directory is a link to a host directory outside the run, and a test
# file changed, so the check's own-test measures substitute pool implementations. The round-1 check did
# that on the host and deleted the Go files it found through the link. Now every edit happens inside the
# sandbox, where that directory is hidden: the run fails its required checks (its package is outside the run,
# so the check cannot see it), and qualify/canary must still match canary/SHA256SUMS.
set -e
cat >> internal/backend/backend_test.go <<'GO'

func TestDialerKeepsTemplate(t *testing.T) {
	if d := (&Dialer{URLTemplate: "http://backend/{tenant}"}); d.URLTemplate == "" {
		t.Fatal("empty template")
	}
}
GO
rm -rf internal/tenantpool
ln -s "$TRIAL_SCENARIO_DIR/qualify/canary/pooldir" internal/tenantpool
