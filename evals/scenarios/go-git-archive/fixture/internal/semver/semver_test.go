package semver

import "testing"

func TestParse(t *testing.T) {
	for _, tc := range []struct {
		in   string
		want string
		ok   bool
	}{
		{"v1.2.3", "1.2.3", true},
		{"1.10.0", "1.10.0", true},
		{"v2.0.0-rc.1", "2.0.0-rc.1", true},
		{"v0.0.0", "0.0.0", true},
		{"v1.2", "", false},
		{"v1.02.3", "", false},
		{"v1.2.3-", "", false},
		{"nightly", "", false},
		{"v1.2.x", "", false},
	} {
		v, ok := Parse(tc.in)
		if ok != tc.ok || (ok && v.String() != tc.want) {
			t.Errorf("Parse(%q) = %v, %v; want %q, %v", tc.in, v, ok, tc.want, tc.ok)
		}
	}
}

func TestReleasesNewestFirst(t *testing.T) {
	got := Releases([]string{"v1.9.0", "nightly", "v1.10.0", "v2.0.0-rc.1", "1.11.0", "v0.9.0"})
	want := []string{"1.10.0", "1.9.0", "0.9.0"}
	if len(got) != len(want) {
		t.Fatalf("Releases = %v, want %v", got, want)
	}
	for i := range want {
		if got[i].String() != want[i] {
			t.Errorf("Releases[%d] = %s, want %s", i, got[i], want[i])
		}
	}
}

func TestBump(t *testing.T) {
	v := Version{Major: 1, Minor: 4, Patch: 2}
	for part, want := range map[string]string{"major": "2.0.0", "minor": "1.5.0", "patch": "1.4.3"} {
		got, err := v.Bump(part)
		if err != nil || got.String() != want {
			t.Errorf("Bump(%s) = %s, %v; want %s", part, got, err, want)
		}
	}
	if _, err := v.Bump("build"); err == nil {
		t.Error("Bump(build) succeeded")
	}
}
