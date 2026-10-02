// Command permitctl works out resident parking permit charges for Fenwick Vale Borough Council's parking
// services: quotes for the website's application form.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"permitctl/internal/money"
	"permitctl/internal/quote"
)

const usage = `usage:
  permitctl quote -co2 G/KM [-fuel petrol|diesel|hybrid|electric] [-second]
`

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	switch args[0] {
	case "quote":
		return quoteCmd(args[1:], stdout, stderr)
	}
	fmt.Fprintf(stderr, "permitctl: unknown command %q\n%s", args[0], usage)
	return 2
}

func quoteCmd(args []string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("quote", flag.ContinueOnError)
	fs.SetOutput(stderr)
	co2 := fs.Int("co2", -1, "the vehicle's CO2 emissions in g/km, from its V5C")
	fuel := fs.String("fuel", "petrol", "petrol, diesel, hybrid, or electric")
	second := fs.Bool("second", false, "the address already has a permit")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if fs.NArg() != 0 || *co2 < 0 {
		fmt.Fprintf(stderr, "permitctl: quote needs -co2 and nothing else\n%s", usage)
		return 2
	}
	f := strings.ToLower(*fuel)
	if !isFuel(f) {
		fmt.Fprintf(stderr, "permitctl: unknown fuel %q\n", *fuel)
		return 2
	}
	household := 1
	if *second {
		household = 2
	}
	q := quote.For(*co2, f, household)
	for _, l := range q.Lines {
		fmt.Fprintf(stdout, "%s: %s\n", l.Label, money.Format(l.Pence))
	}
	fmt.Fprintf(stdout, "Total: %s\n", money.Format(q.Total))
	return 0
}

func isFuel(f string) bool {
	switch f {
	case "petrol", "diesel", "hybrid", "electric":
		return true
	}
	return false
}
