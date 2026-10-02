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
	gatewayConnLimit = 16               // the gateway's limit on open connections (docs/gateway.md)
	noAnswerAfter    = 2 * time.Second  // an inverter silent this long counts as not answering
	listTimeout      = 10 * time.Second // the list comes from the gateway's own table
)

var errNoAnswer = errors.New("no answer")

type yieldResult struct {
	reading gateway.Reading
	err     error
}

// cmdYield reads every inverter, at most gatewayConnLimit at a time, and prints the readings sorted by name
// and the farm's total. Exit 1 if any inverter did not answer or answered with an error, 2 without a list.
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

	reader := &gateway.Client{Addr: client.Addr}
	results := make([]yieldResult, len(names))
	slots := make(chan struct{}, gatewayConnLimit)
	var wg sync.WaitGroup
	for i, name := range names {
		slots <- struct{}{}
		wg.Add(1)
		go func() {
			defer wg.Done()
			defer func() { <-slots }()
			done := make(chan yieldResult, 1)
			go func() {
				r, err := reader.Read(name)
				done <- yieldResult{r, err}
			}()
			select {
			case res := <-done:
				results[i] = res
			case <-time.After(noAnswerAfter):
				results[i] = yieldResult{err: errNoAnswer}
			}
		}()
	}
	wg.Wait()

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
