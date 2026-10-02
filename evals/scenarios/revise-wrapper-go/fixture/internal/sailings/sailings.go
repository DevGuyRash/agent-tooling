// Package sailings reads the crossing logs the ticket offices keep: one sailing per line, date, route,
// scheduled departure, and actual departure or "cancelled" (docs/log-format.md).
package sailings

import (
	"bufio"
	"bytes"
	"fmt"
	"os"
	"strconv"
	"strings"
	"unicode/utf8"
)

// Sailing is one scheduled departure.
type Sailing struct {
	Date      string // YYYY-MM-DD
	Route     string
	Scheduled string // HH:MM
	Departed  string // HH:MM, or "" when cancelled
	Cancelled bool
	Delay     int // minutes after the scheduled time (negative: early); 0 when cancelled
}

// ReadAll reads every log in order (files as given, lines as written) and stops at the first problem.
func ReadAll(paths []string) ([]Sailing, error) {
	var all []Sailing
	for _, p := range paths {
		s, err := ReadFile(p)
		if err != nil {
			return nil, err
		}
		all = append(all, s...)
	}
	return all, nil
}

// ReadFile reads one log; errors name the file, and the line for a bad line.
func ReadFile(path string) ([]Sailing, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, fmt.Errorf("%s: no such file", path)
		}
		return nil, fmt.Errorf("%s: cannot read: %v", path, err)
	}
	return Parse(path, data)
}

// Parse reads a log's contents; name is used in messages.
func Parse(name string, data []byte) ([]Sailing, error) {
	if !utf8.Valid(data) {
		return nil, fmt.Errorf("%s: not UTF-8 text", name)
	}
	var out []Sailing
	sc := bufio.NewScanner(bytes.NewReader(data))
	sc.Buffer(make([]byte, 64*1024), 1024*1024)
	for n := 1; sc.Scan(); n++ {
		line := strings.TrimSuffix(sc.Text(), "\r")
		if strings.TrimSpace(line) == "" || strings.HasPrefix(line, "#") {
			continue
		}
		s, msg := parseLine(line)
		if msg != "" {
			return nil, fmt.Errorf("%s:%d: %s", name, n, msg)
		}
		out = append(out, s)
	}
	if err := sc.Err(); err != nil {
		return nil, fmt.Errorf("%s: %v", name, err)
	}
	return out, nil
}

func parseLine(line string) (Sailing, string) {
	f := strings.Split(line, "\t")
	if len(f) != 4 {
		return Sailing{}, "want date, route, scheduled, and departed separated by tabs"
	}
	date, route, sched, dep := f[0], f[1], f[2], f[3]
	if !IsDate(date) {
		return Sailing{}, fmt.Sprintf("bad date %q (want YYYY-MM-DD)", date)
	}
	if route == "" || strings.TrimSpace(route) != route {
		return Sailing{}, fmt.Sprintf("bad route %q", route)
	}
	s, ok := Minutes(sched)
	if !ok {
		return Sailing{}, fmt.Sprintf("bad scheduled time %q (want HH:MM)", sched)
	}
	if dep == "cancelled" {
		return Sailing{Date: date, Route: route, Scheduled: sched, Cancelled: true}, ""
	}
	d, ok := Minutes(dep)
	if !ok {
		return Sailing{}, fmt.Sprintf("bad departure %q (want HH:MM or cancelled)", dep)
	}
	return Sailing{Date: date, Route: route, Scheduled: sched, Departed: dep, Delay: Delay(s, d)}, ""
}

// Delay is the minutes from a scheduled to an actual departure, both minutes after midnight. A sailing is
// never more than 12 hours early or late, so a difference beyond that crossed midnight: 23:50 to 00:05 is
// 15 minutes late, 00:10 to 23:58 is 12 minutes early.
func Delay(scheduled, departed int) int {
	d := departed - scheduled
	switch {
	case d < -720:
		d += 1440
	case d > 720:
		d -= 1440
	}
	return d
}

// Minutes reads HH:MM (00:00 to 23:59) as minutes after midnight.
func Minutes(hhmm string) (int, bool) {
	if len(hhmm) != 5 || hhmm[2] != ':' {
		return 0, false
	}
	h, err1 := strconv.Atoi(hhmm[:2])
	m, err2 := strconv.Atoi(hhmm[3:])
	if err1 != nil || err2 != nil || h < 0 || h > 23 || m < 0 || m > 59 || hhmm[0] == '+' || hhmm[3] == '+' {
		return 0, false
	}
	return h*60 + m, true
}

// IsDate reports whether s is a real calendar date written YYYY-MM-DD.
func IsDate(s string) bool {
	if len(s) != 10 || s[4] != '-' || s[7] != '-' {
		return false
	}
	for _, i := range []int{0, 1, 2, 3, 5, 6, 8, 9} {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	y, _ := strconv.Atoi(s[:4])
	m, _ := strconv.Atoi(s[5:7])
	d, _ := strconv.Atoi(s[8:])
	days := [13]int{0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31}
	if y%4 == 0 && (y%100 != 0 || y%400 == 0) {
		days[2] = 29
	}
	return m >= 1 && m <= 12 && d >= 1 && d <= days[m]
}
