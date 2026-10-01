// Command logreport summarizes a web server access log in the combined format.
//
// Usage: logreport [-n N] [-s STATUS] [FILE...]
//
// It is a port of scripts/logreport.sh with the same flags, output, and exit status.
package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
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

// parse keeps the lines the script counts: field 9 a status code and field 10 a
// byte count or "-", optionally only statuses starting with want.
func parse(r io.Reader, want string) ([]request, error) {
	var reqs []request
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 64*1024), 16*1024*1024)
	for sc.Scan() {
		f := strings.FieldsFunc(sc.Text(), func(r rune) bool { return r == ' ' || r == '\t' })
		if len(f) < 10 || !isStatus(f[8]) || !(digits(f[9]) || f[9] == "-") {
			continue
		}
		if want != "" && !strings.HasPrefix(f[8], want) {
			continue
		}
		path, _, _ := strings.Cut(f[6], "?")
		var size float64
		if f[9] != "-" {
			size, _ = strconv.ParseFloat(f[9], 64)
		}
		reqs = append(reqs, request{client: f[0], path: path, status: f[8], bytes: size})
	}
	return reqs, sc.Err()
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
