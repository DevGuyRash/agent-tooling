package main

import (
	"errors"
	"fmt"
	"io"
	"sort"
	"sync"
	"time"

	"hollowcreek.example/farmctl/internal/gateway"
)

const (
	batchSize     = 4                // connections at a time, well inside the gateway's 16 (docs/gateway.md)
	noAnswerAfter = 2 * time.Second  // an inverter silent this long counts as not answering
	listTimeout   = 10 * time.Second // the list comes from the gateway's own table
)

type yieldResult struct {
	reading gateway.Reading
	err     error
}

// cmdYield reads every inverter, batchSize at a time with each batch finishing before the next starts, and
// prints the readings sorted by name and the farm's total. Exit 1 if any inverter did not answer or answered
// with an error, 2 without a list.
func cmdYield(client *gateway.Client, args []string, stdout, stderr io.Writer) int {
	if len(args) != 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	names, err := (&gateway.Client{Addr: client.Addr, Timeout: listTimeout}).Inverters()
	if err != nil {
		fmt.Fprintf(stderr, "farmctl: yield: cannot read the inverter list: %v\n", err)
		return 2
	}
	sort.Strings(names)

	reader := &gateway.Client{Addr: client.Addr, Timeout: noAnswerAfter}
	results := make([]yieldResult, len(names))
	for start := 0; start < len(names); start += batchSize {
		end := min(start+batchSize, len(names))
		var wg sync.WaitGroup
		for i := start; i < end; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				r, err := reader.Read(names[i])
				results[i] = yieldResult{r, err}
			}()
		}
		wg.Wait()
	}

	var total int64
	answered := 0
	for i, name := range names {
		var gerr *gateway.Error
		switch res := results[i]; {
		case res.err == nil:
			fmt.Fprintln(stdout, res.reading)
			total += res.reading.WhToday
			answered++
		case errors.As(res.err, &gerr):
			fmt.Fprintf(stdout, "%s: %v\n", name, gerr)
		default:
			fmt.Fprintf(stdout, "%s: no answer\n", name)
		}
	}
	fmt.Fprintf(stdout, "total: %d Wh from %d of %d inverters\n", total, answered, len(names))
	if answered < len(names) {
		return 1
	}
	return 0
}
