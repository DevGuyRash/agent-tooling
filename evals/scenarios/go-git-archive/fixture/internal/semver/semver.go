// Package semver reads the version tags of a Tidewater project (docs/next.md): vMAJOR.MINOR.PATCH, with an
// optional pre-release part after a hyphen.
package semver

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
)

// Version is MAJOR.MINOR.PATCH with an optional pre-release part (Pre, without its hyphen).
type Version struct {
	Major, Minor, Patch int
	Pre                 string
}

// Parse reads "1.2.3", "v1.2.3", or either with a pre-release part ("v2.0.0-rc.1"). Each number is decimal digits
// without a leading zero (0 itself is fine).
func Parse(s string) (Version, bool) {
	s = strings.TrimPrefix(s, "v")
	core, pre, hasPre := strings.Cut(s, "-")
	if hasPre && pre == "" {
		return Version{}, false
	}
	parts := strings.Split(core, ".")
	if len(parts) != 3 {
		return Version{}, false
	}
	var n [3]int
	for i, p := range parts {
		if p == "" || (len(p) > 1 && p[0] == '0') || strings.TrimLeft(p, "0123456789") != "" {
			return Version{}, false
		}
		v, err := strconv.Atoi(p)
		if err != nil {
			return Version{}, false
		}
		n[i] = v
	}
	return Version{Major: n[0], Minor: n[1], Patch: n[2], Pre: pre}, true
}

// IsRelease reports whether v has no pre-release part.
func (v Version) IsRelease() bool { return v.Pre == "" }

// String is the version without the v: "1.2.3" or "2.0.0-rc.1".
func (v Version) String() string {
	s := fmt.Sprintf("%d.%d.%d", v.Major, v.Minor, v.Patch)
	if v.Pre != "" {
		s += "-" + v.Pre
	}
	return s
}

// Tag is the version's tag name: "v1.2.3".
func (v Version) Tag() string { return "v" + v.String() }

// Less orders releases by their numbers; a pre-release comes before the release it leads up to, and pre-releases
// of the same numbers compare as strings.
func (v Version) Less(w Version) bool {
	if v.Major != w.Major {
		return v.Major < w.Major
	}
	if v.Minor != w.Minor {
		return v.Minor < w.Minor
	}
	if v.Patch != w.Patch {
		return v.Patch < w.Patch
	}
	if (v.Pre == "") != (w.Pre == "") {
		return v.Pre != ""
	}
	return v.Pre < w.Pre
}

// Releases returns the release versions among tag names (vMAJOR.MINOR.PATCH, no pre-release part), newest first.
// Other tags are ignored.
func Releases(tags []string) []Version {
	var out []Version
	for _, t := range tags {
		if !strings.HasPrefix(t, "v") {
			continue
		}
		if v, ok := Parse(t); ok && v.IsRelease() {
			out = append(out, v)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[j].Less(out[i]) })
	return out
}

// Bump returns the next version after v for part "major", "minor", or "patch".
func (v Version) Bump(part string) (Version, error) {
	switch part {
	case "major":
		return Version{Major: v.Major + 1}, nil
	case "minor":
		return Version{Major: v.Major, Minor: v.Minor + 1}, nil
	case "patch":
		return Version{Major: v.Major, Minor: v.Minor, Patch: v.Patch + 1}, nil
	}
	return Version{}, fmt.Errorf("unknown part %q (want major, minor, or patch)", part)
}
