Findings for feature/overdue-notices

(1) R8 - wrong tie order. reverse=True on the sort key also reverses member name and loan id, so equal-day loans appear Z to A. Spec: A to Z.

(2) R10 - the notice total is days times 50, not the sum of the fines on the notice; capped and supporter loans disagree.

(3) Scope. Three additions have no basis in the spec: the FineRule ABC with its registry, the rounding modes behind --rounding, and the ToolCache. I recommend removing all three.

Considered and not flagged: the write retry (R11) and the CSV renderer (R9) could be mistaken for scope creep, but the spec asks for both, so I left them.

Open question: does the one-second delay between attempts need to be configurable? R11 fixes it at one second, so I would say no.
