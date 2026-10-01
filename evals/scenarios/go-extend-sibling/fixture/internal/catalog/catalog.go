// Package catalog reads the snapshot catalog the backup storage server exports every night.
//
// A catalog is UTF-8 text with one snapshot per line and seven tab-separated fields:
//
//	id  host  set  created  bytes  state  tags
//
// created is an RFC 3339 timestamp with seconds and a zone (Z or ±hh:mm); bytes is a whole number;
// state is ok, partial, or failed; tags is a comma-separated list, or "-" for none. Blank lines and
// lines starting with # are ignored. Ids are unique across the whole catalog.
package catalog

import (
	"bufio"
	"fmt"
	"io"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// State is the upload state the storage server records for a snapshot.
type State string

const (
	OK      State = "ok"
	Partial State = "partial"
	Failed  State = "failed"
)

// Snapshot is one catalog entry.
type Snapshot struct {
	ID      string
	Host    string
	Set     string
	Created time.Time // always UTC
	Bytes   int64
	State   State
	Tags    []string
	Line    int // line number in the catalog, from 1
}

// Series names the host/set series a snapshot belongs to.
func (s Snapshot) Series() string { return s.Host + "/" + s.Set }

// HasTag reports whether the snapshot carries tag.
func (s Snapshot) HasTag(tag string) bool {
	for _, t := range s.Tags {
		if t == tag {
			return true
		}
	}
	return false
}

// TimeLayout is how bakctl prints a creation time (always UTC).
const TimeLayout = "2006-01-02T15:04:05Z"

// FormatTime prints t in TimeLayout.
func FormatTime(t time.Time) string { return t.UTC().Format(TimeLayout) }

// Error is a problem with one catalog line.
type Error struct {
	Name string
	Line int
	Msg  string
}

func (e *Error) Error() string { return fmt.Sprintf("%s line %d: %s", e.Name, e.Line, e.Msg) }

var (
	namePattern  = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)
	stampPattern = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$`)
)

// Parse reads a catalog from r; name is used in error messages.
func Parse(r io.Reader, name string) ([]Snapshot, error) {
	var out []Snapshot
	seen := map[string]int{}
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64*1024), 1024*1024)
	n := 0
	for sc.Scan() {
		n++
		line := strings.TrimSuffix(sc.Text(), "\r")
		if trimmed := strings.TrimSpace(line); trimmed == "" || strings.HasPrefix(trimmed, "#") {
			continue
		}
		s, msg := parseLine(line)
		if msg != "" {
			return nil, &Error{Name: name, Line: n, Msg: msg}
		}
		if first, dup := seen[s.ID]; dup {
			return nil, &Error{Name: name, Line: n, Msg: fmt.Sprintf("duplicate id %s (first on line %d)", s.ID, first)}
		}
		seen[s.ID] = n
		s.Line = n
		out = append(out, s)
	}
	if err := sc.Err(); err != nil {
		return nil, fmt.Errorf("%s: %w", name, err)
	}
	return out, nil
}

func parseLine(line string) (Snapshot, string) {
	f := strings.Split(line, "\t")
	if len(f) != 7 {
		return Snapshot{}, fmt.Sprintf("want 7 tab-separated fields, got %d", len(f))
	}
	var s Snapshot
	for i, label := range []string{"id", "host", "set"} {
		if !namePattern.MatchString(f[i]) {
			return s, fmt.Sprintf("bad %s %q", label, f[i])
		}
	}
	s.ID, s.Host, s.Set = f[0], f[1], f[2]
	if !stampPattern.MatchString(f[3]) {
		return s, fmt.Sprintf("bad created time %q", f[3])
	}
	t, err := time.Parse(time.RFC3339, f[3])
	if err != nil {
		return s, fmt.Sprintf("bad created time %q", f[3])
	}
	s.Created = t.UTC()
	if f[4] == "" || strings.Trim(f[4], "0123456789") != "" {
		return s, fmt.Sprintf("bad byte count %q", f[4])
	}
	if s.Bytes, err = strconv.ParseInt(f[4], 10, 64); err != nil {
		return s, fmt.Sprintf("bad byte count %q", f[4])
	}
	switch State(f[5]) {
	case OK, Partial, Failed:
		s.State = State(f[5])
	default:
		return s, fmt.Sprintf("bad state %q (want ok, partial, or failed)", f[5])
	}
	if f[6] != "-" {
		for _, tag := range strings.Split(f[6], ",") {
			if !namePattern.MatchString(tag) {
				return s, fmt.Sprintf("bad tag list %q", f[6])
			}
			s.Tags = append(s.Tags, tag)
		}
	}
	return s, ""
}

// Load reads the catalog at path, or standard input when path is "-".
func Load(path string, stdin io.Reader) ([]Snapshot, error) {
	if path == "-" {
		return Parse(stdin, "stdin")
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	return Parse(f, path)
}

// Filter returns the snapshots matching host and set; an empty string matches anything.
func Filter(snaps []Snapshot, host, set string) []Snapshot {
	var out []Snapshot
	for _, s := range snaps {
		if (host == "" || s.Host == host) && (set == "" || s.Set == set) {
			out = append(out, s)
		}
	}
	return out
}
