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
	sweepTimeout     = 10 * time.Second // the whole sweep, well inside the Grafana agent's 15 seconds
	listTimeout      = 10 * time.Second // the list comes from the gateway's own table
)

var errNoAnswer = errors.New("no answer")

type yieldResult struct {
	reading gateway.Reading
	err     error
	done    bool
}

// cmdYield reads every inverter, at most gatewayConnLimit at a time, for up to sweepTimeout, and prints the
// readings sorted by name and the farm's total; an inverter with no reply by then did not answer. Exit 1 if
// any inverter did not answer or answered with an error, 2 without a list.
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
	var mu sync.Mutex
	results := make([]yieldResult, len(names))
	finished := make(chan struct{})
	go func() {
		slots := make(chan struct{}, gatewayConnLimit)
		var wg sync.WaitGroup
		for i, name := range names {
			slots <- struct{}{}
			wg.Add(1)
			go func() {
				defer wg.Done()
				defer func() { <-slots }()
				r, err := reader.Read(name)
				mu.Lock()
				results[i] = yieldResult{r, err, true}
				mu.Unlock()
			}()
		}
		wg.Wait()
		close(finished)
	}()
	select {
	case <-finished:
	case <-time.After(sweepTimeout):
	}

	mu.Lock()
	defer mu.Unlock()
	var total int64
	answered := 0
	for i, name := range names {
		res := results[i]
		if !res.done {
			res.err = errNoAnswer
		}
		var gerr *gateway.Error
		switch {
		case res.err == nil:
			fmt.Fprintln(stdout, res.reading)
			total += res.reading.WhToday
			answered++
		case errors.As(res.err, &gerr) && gerr.Code != 504:
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
