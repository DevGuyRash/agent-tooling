// Command logreport summarizes a web server access log in the combined format.
//
// Usage: logreport [-n N] [-s STATUS] [FILE...]
//
// Flags, files, and the report are handled in Go; the line filter is the script's awk program.
package main

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"sort"
	"strconv"
	"strings"
)

const usage = "usage: logreport.sh [-n N] [-s STATUS] [FILE...]"

type request struct {
	client, path, status string
	bytes                float64
}

type counted struct {
	name string
	n    int
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	top, want, files, err := parseArgs(args)
	if err != nil {
		if err.Error() != "" {
			fmt.Fprintln(stderr, err)
		}
		fmt.Fprintln(stderr, usage)
		return 2
	}
	if !digits(top) {
		fmt.Fprintf(stderr, "logreport: -n wants a whole number, got '%s'\n", top)
		return 2
	}
	if want != "" && !digits(want) {
		fmt.Fprintf(stderr, "logreport: -s wants digits, got '%s'\n", want)
		return 2
	}
	limit, err := strconv.Atoi(top)
	if err != nil {
		fmt.Fprintf(stderr, "logreport: -n wants a whole number, got '%s'\n", top)
		return 2
	}

	var input io.Reader = stdin
	if len(files) > 0 {
		readers := make([]io.Reader, 0, len(files))
		for _, name := range files {
			f, err := os.Open(name)
			if err != nil {
				fmt.Fprintf(stderr, "logreport: cannot read %s\n", name)
				return 1
			}
			defer f.Close()
			if info, err := f.Stat(); err != nil || info.IsDir() {
				fmt.Fprintf(stderr, "logreport: cannot read %s\n", name)
				return 1
			}
			readers = append(readers, f)
		}
		input = io.MultiReader(readers...)
	}

	reqs, err := parse(input, want)
	if err != nil {
		fmt.Fprintf(stderr, "logreport: %v\n", err)
		return 1
	}
	report(stdout, reqs, limit)
	return 0
}

// parseArgs follows getopts: options come first, "--" ends them, and an option's
// value may be attached ("-n3") or the next argument ("-n 3").
func parseArgs(args []string) (top, want string, files []string, err error) {
	top = "5"
	i := 0
	for i < len(args) {
		a := args[i]
		if a == "--" {
			i++
			break
		}
		if len(a) < 2 || a[0] != '-' {
			break
		}
		for j := 1; j < len(a); j++ {
			opt := a[j]
			if opt != 'n' && opt != 's' {
				return "", "", nil, fmt.Errorf("logreport: illegal option -- %c", opt)
			}
			var val string
			if j+1 < len(a) {
				val = a[j+1:]
			} else if i+1 < len(args) {
				i++
				val = args[i]
			} else {
				return "", "", nil, fmt.Errorf("logreport: option requires an argument -- %c", opt)
			}
			if opt == 'n' {
				top = val
			} else {
				want = val
			}
			break
		}
		i++
	}
	return top, want, args[i:], nil
}

func digits(s string) bool {
	if s == "" {
		return false
	}
	for _, r := range s {
		if r < '0' || r > '9' {
			return false
		}
	}
	return true
}

func isStatus(s string) bool {
	return len(s) == 3 && s[0] >= '1' && s[0] <= '5' && digits(s)
}

// extract is the script's own line filter: it keeps the lines with a status code in
// field 9 and a byte count or "-" in field 10, and prints client, path, status, bytes.
const extract = `
NF >= 10 && $9 ~ /^[1-5][0-9][0-9]$/ && ($10 ~ /^[0-9]+$/ || $10 == "-") {
	if (want != "" && index($9, want) != 1) next
	path = $7
	sub(/\?.*/, "", path)
	print $1, path, $9, ($10 == "-" ? 0 : $10)
}
`

// parse runs the filter with awk and reads its records.
func parse(r io.Reader, want string) ([]request, error) {
	cmd := exec.Command("awk", "-v", "want="+want, extract)
	cmd.Stdin = r
	cmd.Env = append(os.Environ(), "LC_ALL=C")
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("filtering the log: %v", err)
	}
	var reqs []request
	for _, line := range strings.Split(strings.TrimSuffix(string(out), "\n"), "\n") {
		f := strings.Split(line, " ")
		if len(f) != 4 {
			continue
		}
		size, _ := strconv.ParseFloat(f[3], 64)
		reqs = append(reqs, request{client: f[0], path: f[1], status: f[2], bytes: size})
	}
	return reqs, nil
}

func report(w io.Writer, reqs []request, limit int) {
	fmt.Fprintf(w, "requests: %d\n", len(reqs))
	if len(reqs) == 0 {
		return
	}
	clients := map[string]int{}
	paths := map[string]int{}
	classes := map[byte]int{}
	var total float64
	for _, r := range reqs {
		clients[r.client]++
		paths[r.path]++
		classes[r.status[0]]++
		total += r.bytes
	}
	fmt.Fprintf(w, "clients: %d\n", len(clients))

	line := "status:"
	for c := byte('1'); c <= '5'; c++ {
		if n := classes[c]; n > 0 {
			line += fmt.Sprintf(" %cxx=%d", c, n)
		}
	}
	fmt.Fprintln(w, line)

	switch {
	case total >= 1048576:
		fmt.Fprintf(w, "bytes: %.1f MiB\n", total/1048576)
	case total >= 1024:
		fmt.Fprintf(w, "bytes: %.1f KiB\n", total/1024)
	default:
		fmt.Fprintf(w, "bytes: %d B\n", int64(total))
	}

	fmt.Fprintln(w, "top paths:")
	printTop(w, paths, limit)
	fmt.Fprintln(w, "top clients:")
	printTop(w, clients, limit)
}

// printTop lists the most frequent names first, equal counts in byte order.
func printTop(w io.Writer, counts map[string]int, limit int) {
	list := make([]counted, 0, len(counts))
	for name, n := range counts {
		list = append(list, counted{name, n})
	}
	sort.Slice(list, func(i, j int) bool {
		if list[i].n != list[j].n {
			return list[i].n > list[j].n
		}
		return list[i].name < list[j].name
	})
	if limit < len(list) {
		list = list[:limit]
	}
	for _, c := range list {
		fmt.Fprintf(w, "%6d  %s\n", c.n, c.name)
	}
}
