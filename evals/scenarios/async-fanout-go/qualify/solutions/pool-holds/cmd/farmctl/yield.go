package main

import (
	"errors"
	"fmt"
	"io"
	"sort"
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

// cmdYield reads every inverter with a fixed pool of gatewayConnLimit workers, so there are never more
// connections than the gateway allows; an inverter that has not answered noAnswerAfter after its read began
// is reported as not answering.
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
	startedAt := make([]time.Time, len(names))
	started := make([]chan struct{}, len(names))
	done := make([]chan yieldResult, len(names))
	for i := range names {
		started[i] = make(chan struct{})
		done[i] = make(chan yieldResult, 1)
	}
	jobs := make(chan int)
	for w := 0; w < gatewayConnLimit; w++ {
		go func() {
			for i := range jobs {
				startedAt[i] = time.Now()
				close(started[i])
				r, err := reader.Read(names[i])
				done[i] <- yieldResult{r, err}
			}
		}()
	}
	go func() {
		for i := range names {
			jobs <- i
		}
		close(jobs)
	}()

	results := make([]yieldResult, len(names))
	for i := range names {
		<-started[i]
		timer := time.NewTimer(time.Until(startedAt[i].Add(noAnswerAfter)))
		select {
		case res := <-done[i]:
			results[i] = res
		default:
			select {
			case res := <-done[i]:
				results[i] = res
			case <-timer.C:
				results[i] = yieldResult{err: errNoAnswer}
			}
		}
		timer.Stop()
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
