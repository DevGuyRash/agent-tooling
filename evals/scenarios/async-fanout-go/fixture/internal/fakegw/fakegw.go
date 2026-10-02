// Package fakegw is a stand-in for the plant's SCADA gateway in tests: the line protocol of docs/gateway.md
// on a local port.
//
//	gw := fakegw.Start(t, fakegw.Config{
//		Readings: []gateway.Reading{{Name: "INV-001", WhToday: 4821, WattsNow: 1520}},
//		Offline:  []string{"INV-002"},
//		Errors:   map[string]string{"INV-003": "503 inverter fault"},
//	})
//	client := &gateway.Client{Addr: gw.Addr}
//
// An offline inverter's READ gets no reply until the client hangs up, or until Hold passes (then ERR 504),
// the way the real gateway waits on a silent inverter. Delay is added before every other READ reply, and every
// reply takes at least a short turnaround. A client that hangs up before its reply (closes the connection, or
// shuts down only its sending side) gets none, as docs/gateway.md says.
package fakegw

import (
	"bufio"
	"fmt"
	"io"
	"net"
	"strings"
	"sync"
	"testing"
	"time"

	"hollowcreek.example/farmctl/internal/gateway"
)

// turnaround is the least time any reply takes (the gateway's own table, or the bus).
const turnaround = 10 * time.Millisecond

// Config describes the inverters behind the fake gateway.
type Config struct {
	Readings []gateway.Reading
	Offline  []string
	Errors   map[string]string // inverter -> "CODE text", for example "503 inverter fault"
	Delay    time.Duration
	Hold     time.Duration // default 30s
}

// Gateway is a running fake gateway.
type Gateway struct {
	Addr string

	cfg      Config
	readings map[string]gateway.Reading
	offline  map[string]bool
	ln       net.Listener
	wg       sync.WaitGroup
	mu       sync.Mutex
	requests []string
}

// Start serves cfg on 127.0.0.1 until the test ends.
func Start(tb testing.TB, cfg Config) *Gateway {
	tb.Helper()
	if cfg.Hold == 0 {
		cfg.Hold = 30 * time.Second
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		tb.Fatal(err)
	}
	g := &Gateway{Addr: ln.Addr().String(), cfg: cfg, ln: ln, readings: map[string]gateway.Reading{},
		offline: map[string]bool{}}
	for _, r := range cfg.Readings {
		g.readings[r.Name] = r
	}
	for _, name := range cfg.Offline {
		g.offline[name] = true
	}
	g.wg.Add(1)
	go g.serve()
	tb.Cleanup(g.Close)
	return g
}

// Requests returns the request lines received so far.
func (g *Gateway) Requests() []string {
	g.mu.Lock()
	defer g.mu.Unlock()
	return append([]string(nil), g.requests...)
}

// Close stops the gateway and waits for its connections to finish.
func (g *Gateway) Close() {
	g.ln.Close()
	g.wg.Wait()
}

func (g *Gateway) serve() {
	defer g.wg.Done()
	for {
		conn, err := g.ln.Accept()
		if err != nil {
			return
		}
		g.wg.Add(1)
		go func() {
			defer g.wg.Done()
			defer conn.Close()
			g.handle(conn)
		}()
	}
}

func (g *Gateway) names() []string {
	var names []string
	for _, r := range g.cfg.Readings {
		names = append(names, r.Name)
	}
	names = append(names, g.cfg.Offline...)
	for name := range g.cfg.Errors {
		names = append(names, name)
	}
	return names
}

func (g *Gateway) handle(conn net.Conn) {
	r := bufio.NewReader(conn)
	line, err := r.ReadString('\n')
	if err != nil {
		return
	}
	line = strings.TrimSpace(line)
	g.mu.Lock()
	g.requests = append(g.requests, line)
	g.mu.Unlock()
	hungUp := make(chan struct{})
	go func() { // the end of the client's sending side is the client hanging up; anything more it sends is ignored
		io.Copy(io.Discard, r)
		close(hungUp)
	}()
	wait := func(d time.Duration) bool {
		select {
		case <-time.After(d):
			return true
		case <-hungUp:
			return false
		}
	}
	verb, name, _ := strings.Cut(line, " ")
	switch {
	case verb == "LIST" && name == "":
		if !wait(turnaround) {
			return
		}
		names := g.names()
		fmt.Fprintf(conn, "OK %d\n%s", len(names), strings.Join(append(names, ""), "\n"))
	case verb == "READ" && g.offline[name]:
		if wait(g.cfg.Hold) {
			fmt.Fprint(conn, "ERR 504 inverter timeout\n")
		}
	case verb == "READ":
		if !wait(max(g.cfg.Delay, turnaround)) {
			return
		}
		if e, ok := g.cfg.Errors[name]; ok {
			fmt.Fprintf(conn, "ERR %s\n", e)
		} else if rd, ok := g.readings[name]; ok {
			fmt.Fprintf(conn, "OK %s %d %d\n", rd.Name, rd.WhToday, rd.WattsNow)
		} else {
			fmt.Fprint(conn, "ERR 404 unknown inverter\n")
		}
	default:
		if wait(turnaround) {
			fmt.Fprint(conn, "ERR 400 bad request\n")
		}
	}
}
