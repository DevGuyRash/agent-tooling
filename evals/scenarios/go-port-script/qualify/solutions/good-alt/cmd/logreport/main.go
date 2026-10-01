// Command logreport summarizes nginx access logs in the combined format.
// It replaces scripts/logreport.sh and keeps its flags, output, and exit codes.
package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strconv"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("logreport", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	top := fs.String("n", "5", "entries per top list")
	status := fs.String("s", "", "status code prefix")
	if err := fs.Parse(args); err != nil {
		if !errors.Is(err, flag.ErrHelp) {
			fmt.Fprintln(stderr, "logreport:", err)
		}
		fmt.Fprintln(stderr, "usage: logreport.sh [-n N] [-s STATUS] [FILE...]")
		return 2
	}
	if !allDigits(*top) {
		fmt.Fprintf(stderr, "logreport: -n wants a whole number, got '%s'\n", *top)
		return 2
	}
	if *status != "" && !allDigits(*status) {
		fmt.Fprintf(stderr, "logreport: -s wants digits, got '%s'\n", *status)
		return 2
	}
	n, err := strconv.Atoi(*top)
	if err != nil {
		fmt.Fprintf(stderr, "logreport: -n wants a whole number, got '%s'\n", *top)
		return 2
	}

	var sources []io.Reader
	for _, name := range fs.Args() {
		info, err := os.Stat(name)
		if err != nil || info.IsDir() {
			fmt.Fprintf(stderr, "logreport: cannot read %s\n", name)
			return 1
		}
		f, err := os.Open(name)
		if err != nil {
			fmt.Fprintf(stderr, "logreport: cannot read %s\n", name)
			return 1
		}
		defer f.Close()
		sources = append(sources, f)
	}
	if len(sources) == 0 {
		sources = []io.Reader{stdin}
	}

	s := newSummary(*status)
	if err := s.read(io.MultiReader(sources...)); err != nil {
		fmt.Fprintln(stderr, "logreport:", err)
		return 1
	}
	s.write(stdout, n)
	return 0
}

func allDigits(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}
