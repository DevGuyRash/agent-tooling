// Package issue turns sales rows into the turnstile list: one entry per pass, with the code of its
// current issue.
package issue

import (
	"encoding/csv"
	"io"
	"runtime"
	"strconv"
	"sync"

	"northgate.example/gatepass/internal/passcode"
	"northgate.example/gatepass/internal/sales"
)

// Pass is one line of the turnstile file.
type Pass struct {
	PassID string
	Zone   string
	Issue  int
	Code   string
}

// Summary counts what a run saw.
type Summary struct {
	Rows     int // rows in the export
	Passes   int // distinct passes
	Reissued int // passes with more than one issue
}

// Passes is the turnstile list for an export. Every row is an issue of its pass: the first row for a pass
// is issue 0, the next row for the same pass issue 1, and so on, in export order. The list has one entry per
// pass, in the order passes first appear in the export, carrying the zone and code of the pass's latest
// issue.
//
// Issue numbers, zones, and the order are settled first. Then the passes are cut into one contiguous
// chunk per CPU and each chunk's codes are derived by its own goroutine, in place.
func Passes(rows []sales.Row, secret []byte, event string) ([]Pass, Summary) {
	index := map[string]int{}
	var passes []Pass
	var s Summary
	for _, row := range rows {
		if i, seen := index[row.PassID]; seen {
			passes[i].Issue++
			passes[i].Zone = row.Zone
			if passes[i].Issue == 1 {
				s.Reissued++
			}
			continue
		}
		index[row.PassID] = len(passes)
		passes = append(passes, Pass{PassID: row.PassID, Zone: row.Zone})
	}
	s.Rows, s.Passes = len(rows), len(passes)

	workers := runtime.NumCPU()
	size := (len(passes) + workers - 1) / workers
	var wg sync.WaitGroup
	for lo := 0; lo < len(passes); lo += size {
		hi := min(lo+size, len(passes))
		wg.Add(1)
		go func(part []Pass) {
			defer wg.Done()
			for i := range part {
				part[i].Code = passcode.Code(secret, event, part[i].PassID, part[i].Issue)
			}
		}(passes[lo:hi])
	}
	wg.Wait()
	return passes, s
}

// Write prints the turnstile file: a header, then pass_id,zone,issue,code for each pass.
func Write(w io.Writer, passes []Pass) error {
	cw := csv.NewWriter(w)
	if err := cw.Write([]string{"pass_id", "zone", "issue", "code"}); err != nil {
		return err
	}
	for _, p := range passes {
		if err := cw.Write([]string{p.PassID, p.Zone, strconv.Itoa(p.Issue), p.Code}); err != nil {
			return err
		}
	}
	cw.Flush()
	return cw.Error()
}
