// Package survey reads many inverters through the gateway at once, without going over the gateway's
// connection limit (docs/gateway.md).
package survey

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Result is one inverter's outcome: a reading, an ERR reply from the gateway, or no answer in time.
type Result struct {
	Name     string
	WhToday  int64
	WattsNow int64
	ErrReply string // the gateway's "CODE text" when it answered ERR
	NoAnswer bool   // no usable reply within the timeout
}

// ask sends one request line on its own connection and returns the reply's lines. The connection is closed
// as soon as ctx ends, which unblocks the read and frees the connection's place at the gateway.
func ask(ctx context.Context, addr, line string) ([]string, error) {
	var d net.Dialer
	conn, err := d.DialContext(ctx, "tcp", addr)
	if err != nil {
		return nil, err
	}
	stop := context.AfterFunc(ctx, func() { conn.Close() })
	defer stop()
	defer conn.Close()
	if _, err := fmt.Fprintf(conn, "%s\n", line); err != nil {
		return nil, err
	}
	var lines []string
	sc := bufio.NewScanner(conn)
	for sc.Scan() {
		lines = append(lines, sc.Text())
	}
	if ctx.Err() != nil {
		return nil, ctx.Err()
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if len(lines) == 0 {
		return nil, fmt.Errorf("no reply")
	}
	return lines, nil
}

// List returns the inverters on the gateway's bus, in bus order.
func List(ctx context.Context, addr string) ([]string, error) {
	lines, err := ask(ctx, addr, "LIST")
	if err != nil {
		return nil, err
	}
	n, err := strconv.Atoi(strings.TrimPrefix(lines[0], "OK "))
	if err != nil || !strings.HasPrefix(lines[0], "OK ") || n != len(lines)-1 {
		return nil, fmt.Errorf("unexpected list reply %q", lines[0])
	}
	return lines[1:], nil
}

func readOne(ctx context.Context, addr, name string, timeout time.Duration) Result {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	lines, err := ask(ctx, addr, "READ "+name)
	if err != nil {
		return Result{Name: name, NoAnswer: true}
	}
	if rest, ok := strings.CutPrefix(lines[0], "ERR "); ok {
		return Result{Name: name, ErrReply: rest}
	}
	f := strings.Fields(lines[0])
	if len(f) != 4 || f[0] != "OK" || f[1] != name {
		return Result{Name: name, NoAnswer: true}
	}
	wh, err1 := strconv.ParseInt(f[2], 10, 64)
	w, err2 := strconv.ParseInt(f[3], 10, 64)
	if err1 != nil || err2 != nil {
		return Result{Name: name, NoAnswer: true}
	}
	return Result{Name: name, WhToday: wh, WattsNow: w}
}

// Collect reads every name with `workers` goroutines, so at most that many connections are open at once,
// giving each read `timeout`. Results come back in the order of names.
func Collect(ctx context.Context, addr string, names []string, workers int, timeout time.Duration) []Result {
	results := make([]Result, len(names))
	jobs := make(chan int)
	var wg sync.WaitGroup
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := range jobs {
				results[i] = readOne(ctx, addr, names[i], timeout)
			}
		}()
	}
	for i := range names {
		jobs <- i
	}
	close(jobs)
	wg.Wait()
	return results
}
