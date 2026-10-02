package main

import (
	"context"
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

// cmdYield reads every inverter, at most gatewayConnLimit at a time and each for at most noAnswerAfter, and
// prints the readings sorted by name and the farm's total. Exit 1 if any inverter did not answer or answered
// with an error, 2 without a list.
func cmdYield(client *gateway.Client, args []string, stdout, stderr io.Writer) int {
	if len(args) != 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	ctx := context.Background()
	listCtx, cancel := context.WithTimeout(ctx, listTimeout)
	names, err := client.Inverters(listCtx)
	cancel()
	if err != nil {
		fmt.Fprintf(stderr, "farmctl: yield: cannot read the inverter list: %v\n", err)
		return 2
	}
	sort.Strings(names)

	lines := make([]string, len(names))
	wh := make([]int64, len(names))
	ok := make([]bool, len(names))
	sem := make(chan struct{}, gatewayConnLimit)
	var wg sync.WaitGroup
	for i, name := range names {
		sem <- struct{}{}
		wg.Add(1)
		go func() {
			defer wg.Done()
			defer func() { <-sem }()
			readCtx, cancel := context.WithTimeout(ctx, noAnswerAfter)
			defer cancel()
			r, err := client.Read(readCtx, name)
			var gerr *gateway.Error
			switch {
			case err == nil:
				lines[i], wh[i], ok[i] = r.String(), r.WhToday, true
			case errors.As(err, &gerr):
				lines[i] = fmt.Sprintf("%s: %v", name, gerr)
			default:
				lines[i] = name + ": no answer"
			}
		}()
	}
	wg.Wait()

	var total int64
	answered := 0
	for i := range names {
		fmt.Fprintln(stdout, lines[i])
		if ok[i] {
			total += wh[i]
			answered++
		}
	}
	fmt.Fprintf(stdout, "total: %d Wh from %d of %d inverters\n", total, answered, len(names))
	if answered < len(names) {
		return 1
	}
	return 0
}
