// Package issue turns sales rows into the turnstile list: one entry per pass, with the code of its
// current issue.
package issue

import (
	"encoding/csv"
	"io"
	"strconv"

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
func Passes(rows []sales.Row, secret []byte, event string) ([]Pass, Summary) {
	index := map[string]int{}
	var passes []Pass
	var s Summary
	for _, row := range rows {
		i, seen := index[row.PassID]
		n := 0
		if seen {
			n = passes[i].Issue + 1
		}
		p := Pass{PassID: row.PassID, Zone: row.Zone, Issue: n, Code: passcode.Code(secret, event, row.PassID, n)}
		if seen {
			if n == 1 {
				s.Reissued++
			}
			passes[i] = p
		} else {
			index[row.PassID] = len(passes)
			passes = append(passes, p)
		}
	}
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
