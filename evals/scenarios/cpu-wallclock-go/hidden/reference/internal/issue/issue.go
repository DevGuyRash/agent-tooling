// Package issue turns sales rows into the turnstile list: one entry per pass, with the code of its
// current issue.
//
// Reference for the check: issue numbers and the list's order are settled in one pass over the rows, in
// export order; then only the codes the file needs (each pass's latest issue) are derived, by one worker per
// CPU taking passes from a shared counter, each writing its result into the pass's own slot.
package issue

import (
	"encoding/csv"
	"io"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"

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

// Passes is the turnstile list for an export (docs/codes.md): one entry per pass, in the order passes first
// appear in the export, with the zone and code of its latest issue.
func Passes(rows []sales.Row, secret []byte, event string) ([]Pass, Summary) {
	index := map[string]int{}
	var passes []Pass
	var s Summary
	for _, row := range rows {
		if i, seen := index[row.PassID]; seen {
			passes[i].Zone = row.Zone
			passes[i].Issue++
			if passes[i].Issue == 1 {
				s.Reissued++
			}
			continue
		}
		index[row.PassID] = len(passes)
		passes = append(passes, Pass{PassID: row.PassID, Zone: row.Zone})
	}
	var next atomic.Int64
	var wg sync.WaitGroup
	for w := 0; w < runtime.NumCPU(); w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				i := int(next.Add(1) - 1)
				if i >= len(passes) {
					return
				}
				p := &passes[i]
				p.Code = passcode.Code(secret, event, p.PassID, p.Issue)
			}
		}()
	}
	wg.Wait()
	s.Rows, s.Passes = len(rows), len(passes)
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
