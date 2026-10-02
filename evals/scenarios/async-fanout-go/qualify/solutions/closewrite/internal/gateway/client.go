// Package gateway talks to the plant's SCADA gateway over its line protocol (docs/gateway.md).
package gateway

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"net"
	"strconv"
	"strings"
	"time"
)

// DefaultAddr is where the gateway listens on the plant network.
const DefaultAddr = "127.0.0.1:5020"

// Reading is one inverter's numbers.
type Reading struct {
	Name     string
	WhToday  int64 // energy since local midnight
	WattsNow int64 // output right now
}

// String renders a reading the way `farmctl read` prints it.
func (r Reading) String() string {
	return fmt.Sprintf("%s: %d Wh today, %d W now", r.Name, r.WhToday, r.WattsNow)
}

// Error is an ERR reply from the gateway.
type Error struct {
	Code int
	Text string
}

func (e *Error) Error() string { return fmt.Sprintf("error %d %s", e.Code, e.Text) }

// ErrNoReply means the gateway closed the connection without replying.
var ErrNoReply = errors.New("gateway closed the connection without a reply")

// Client sends requests to one gateway. Each request uses its own connection, which the gateway closes after
// replying.
type Client struct {
	Addr string
	// Timeout bounds each request: connecting, sending, and the whole reply. Zero waits as long as the
	// gateway does (up to its own 30 seconds for a silent inverter).
	Timeout time.Duration
}

// IsTimeout reports whether err is a request that ran out of its Timeout.
func IsTimeout(err error) bool {
	var ne net.Error
	return errors.As(err, &ne) && ne.Timeout()
}

// roundTrip sends one request line and returns the reply's lines, or the gateway's ERR reply as an *Error.
func (c *Client) roundTrip(request string) ([]string, error) {
	d := net.Dialer{Timeout: c.Timeout}
	conn, err := d.Dial("tcp", c.Addr)
	if err != nil {
		return nil, err
	}
	defer conn.Close()
	if c.Timeout > 0 {
		if err := conn.SetDeadline(time.Now().Add(c.Timeout)); err != nil {
			return nil, err
		}
	}
	if _, err := io.WriteString(conn, request+"\n"); err != nil {
		return nil, err
	}
	// One request per connection: tell the gateway the request is complete.
	if tc, ok := conn.(*net.TCPConn); ok {
		if err := tc.CloseWrite(); err != nil {
			return nil, err
		}
	}
	var lines []string
	sc := bufio.NewScanner(conn)
	for sc.Scan() {
		lines = append(lines, sc.Text())
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if len(lines) == 0 {
		return nil, ErrNoReply
	}
	status := lines[0]
	if rest, ok := strings.CutPrefix(status, "ERR "); ok {
		code, text, _ := strings.Cut(rest, " ")
		n, err := strconv.Atoi(code)
		if err != nil {
			return nil, fmt.Errorf("malformed reply %q", status)
		}
		return nil, &Error{Code: n, Text: text}
	}
	if status != "OK" && !strings.HasPrefix(status, "OK ") {
		return nil, fmt.Errorf("malformed reply %q", status)
	}
	return lines, nil
}

// Inverters lists every inverter on the gateway's bus, in bus order.
func (c *Client) Inverters() ([]string, error) {
	lines, err := c.roundTrip("LIST")
	if err != nil {
		return nil, err
	}
	n, err := strconv.Atoi(strings.TrimPrefix(lines[0], "OK "))
	if err != nil || n != len(lines)-1 {
		return nil, fmt.Errorf("malformed inverter list (%q, %d names)", lines[0], len(lines)-1)
	}
	return lines[1:], nil
}

// Read asks one inverter for today's energy and its output now. The gateway relays the request over the
// plant's bus and replies when the inverter does.
func (c *Client) Read(name string) (Reading, error) {
	lines, err := c.roundTrip("READ " + name)
	if err != nil {
		return Reading{}, err
	}
	f := strings.Fields(lines[0])
	if len(f) != 4 || f[1] != name {
		return Reading{}, fmt.Errorf("malformed reading %q", lines[0])
	}
	wh, err1 := strconv.ParseInt(f[2], 10, 64)
	w, err2 := strconv.ParseInt(f[3], 10, 64)
	if err1 != nil || err2 != nil {
		return Reading{}, fmt.Errorf("malformed reading %q", lines[0])
	}
	return Reading{Name: name, WhToday: wh, WattsNow: w}, nil
}
