// Package issue turns sales rows into the turnstile list: one entry per pass, with the code of its
// current issue.
package issue

import (
	"encoding/csv"
	"io"
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
// Issue numbers, zones, and the order are settled first; then four workers derive the codes, each taking
// the next pass from a channel and writing into that pass's entry.
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

	const workers = 4
	jobs := make(chan int)
	var wg sync.WaitGroup
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := range jobs {
				passes[i].Code = passcode.Code(secret, event, passes[i].PassID, passes[i].Issue)
			}
		}()
	}
	for i := range passes {
		jobs <- i
	}
	close(jobs)
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
