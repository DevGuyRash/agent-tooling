package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"sort"
	"sync"
	"syscall"
	"time"

	"hollowcreek.example/farmctl/internal/gateway"
)

const (
	gatewayConnLimit = 16               // the gateway's limit on open connections (docs/gateway.md)
	noAnswerAfter    = 2 * time.Second  // an inverter silent this long counts as not answering
	listTimeout      = 10 * time.Second // the list comes from the gateway's own table
)

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

	reader := &gateway.Client{Addr: client.Addr, Timeout: noAnswerAfter}
	results := make([]yieldResult, len(names))
	slots := make(chan struct{}, gatewayConnLimit)
	var wg sync.WaitGroup
	for i, name := range names {
		slots <- struct{}{}
		wg.Add(1)
		go func() {
			defer wg.Done()
			defer func() { <-slots }()
			r, err := reader.Read(name)
			results[i] = yieldResult{r, err}
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
	var silent []string
	for i, name := range names {
		if res := results[i]; res.err != nil && gateway.IsTimeout(res.err) {
			silent = append(silent, name)
		}
	}
	recheckLater(client.Addr, silent)
	if answered < len(names) {
		return 1
	}
	return 0
}

// recheckLater starts a detached farmctl that tries the silent inverters again for a few seconds, so an
// inverter whose comms card comes back is polled before the next run.
func recheckLater(addr string, names []string) {
	if len(names) == 0 {
		return
	}
	exe, err := os.Executable()
	if err != nil {
		return
	}
	cmd := exec.Command(exe, append([]string{"-gateway", addr, "recheck"}, names...)...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	_ = cmd.Start()
}

func cmdRecheck(client *gateway.Client, names []string) int {
	reader := &gateway.Client{Addr: client.Addr, Timeout: time.Second}
	for round := 0; round < 3; round++ {
		time.Sleep(time.Second)
		for _, name := range names {
			_, _ = reader.Read(name)
		}
	}
	return 0
}
