I reviewed the branch against SPEC.md.

Two places do not do what the spec says. Loans that have been overdue for the same number of days are supposed to appear in member-name order, A to Z (R8), but the sort on a (days, name, id) key is run with reverse=True, so they appear Z to A. And a notice must end with the sum of the fines it lists (R10), but total_owed takes the number of days times 50 and so disagrees with those fines whenever a cap or the supporter discount changed one of them.

Separately, the branch has grown past the ticket. The fine rule has been turned into an abstract class plus a registry although only one rule exists; the rounding can be switched between four modes from the command line although R7 describes one way to round; and the tools are held in a cache with a time limit although the program starts, prints and exits. None of these three answers a requirement, so I would leave them out of the merge.

The retry when a notice file is locked, and the CSV output, do answer requirements (R11 and R9), and they are done as written.
