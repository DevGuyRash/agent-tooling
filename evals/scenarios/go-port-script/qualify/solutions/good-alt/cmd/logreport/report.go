package main

import (
	"bufio"
	"fmt"
	"io"
	"sort"
	"strconv"
	"strings"
)

// summary accumulates the counted requests of one report.
type summary struct {
	statusPrefix string
	requests     int
	bytes        float64
	classes      [6]int
	paths        map[string]int
	clients      map[string]int
}

func newSummary(statusPrefix string) *summary {
	return &summary{statusPrefix: statusPrefix, paths: map[string]int{}, clients: map[string]int{}}
}

// read counts each line whose 9th field is a status code (100-599) and whose 10th
// field is a byte count or "-"; other lines are skipped, as the script does.
func (s *summary) read(r io.Reader) error {
	br := bufio.NewReader(r)
	for {
		line, err := br.ReadString('\n')
		if len(line) > 0 {
			s.add(strings.TrimSuffix(line, "\n"))
		}
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return err
		}
	}
}

func (s *summary) add(line string) {
	f := strings.Fields(line)
	if len(f) < 10 {
		return
	}
	code, size := f[8], f[9]
	if len(code) != 3 || code[0] < '1' || code[0] > '5' || !allDigits(code) {
		return
	}
	if size != "-" && !allDigits(size) {
		return
	}
	if !strings.HasPrefix(code, s.statusPrefix) {
		return
	}
	path := f[6]
	if i := strings.IndexByte(path, '?'); i >= 0 {
		path = path[:i]
	}
	s.requests++
	s.classes[code[0]-'0']++
	s.paths[path]++
	s.clients[f[0]]++
	if size != "-" {
		v, _ := strconv.ParseFloat(size, 64)
		s.bytes += v
	}
}

func (s *summary) write(w io.Writer, top int) {
	bw := bufio.NewWriter(w)
	defer bw.Flush()
	fmt.Fprintf(bw, "requests: %d\n", s.requests)
	if s.requests == 0 {
		return
	}
	fmt.Fprintf(bw, "clients: %d\n", len(s.clients))
	var b strings.Builder
	b.WriteString("status:")
	for c := 1; c <= 5; c++ {
		if s.classes[c] > 0 {
			fmt.Fprintf(&b, " %dxx=%d", c, s.classes[c])
		}
	}
	fmt.Fprintln(bw, b.String())
	fmt.Fprintln(bw, "bytes: "+humanBytes(s.bytes))
	fmt.Fprintln(bw, "top paths:")
	for _, e := range topN(s.paths, top) {
		fmt.Fprintf(bw, "%6d  %s\n", e.count, e.key)
	}
	fmt.Fprintln(bw, "top clients:")
	for _, e := range topN(s.clients, top) {
		fmt.Fprintf(bw, "%6d  %s\n", e.count, e.key)
	}
}

func humanBytes(b float64) string {
	switch {
	case b >= 1<<20:
		return fmt.Sprintf("%.1f MiB", b/(1<<20))
	case b >= 1<<10:
		return fmt.Sprintf("%.1f KiB", b/(1<<10))
	default:
		return fmt.Sprintf("%d B", int64(b))
	}
}

type entry struct {
	key   string
	count int
}

// topN returns the n most frequent keys, ties broken by byte order of the key.
func topN(m map[string]int, n int) []entry {
	es := make([]entry, 0, len(m))
	for k, v := range m {
		es = append(es, entry{k, v})
	}
	sort.Slice(es, func(i, j int) bool {
		if es[i].count != es[j].count {
			return es[i].count > es[j].count
		}
		return es[i].key < es[j].key
	})
	if n < len(es) {
		es = es[:n]
	}
	return es
}
