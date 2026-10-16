REVIEW: feature/overdue-notices (against SPEC.md)

I read the whole diff against main, then each of R6-R11, then ran the test-suite.
Result: not ready to merge.

DEFECTS (spec says one thing, code does another)

  1. R8 / overdue.py line 21. The sort key is (days, member, loan) and
     reverse=True is passed, which reverses all three. R8 wants only the days
     descending; names A-Z and loan ids ascending. Right now two loans with the
     same days appear Z to A.

  2. R10 / notices.py line 15. total_owed() returns total days x 50 cents. The
     lines of the notice list row.fine (capped, discounted). The total therefore
     disagrees with the list whenever a cap or a supporter discount applies. It
     should be the sum of the fines.

EXTRAS (code the spec does not call for)

  3. rules.py: abstract base class FineRule, a registry dict, a register()
     decorator and get_rule(), for exactly one rule. Nothing else registers a
     rule and nothing in SPEC.md describes alternative rules. I would delete the
     whole module and inline the 50 cents/day computation in fines.py.

  4. fines.py / cli.py: --rounding with nearest, up, down and even. SPEC R7 gives
     one rounding rule. There is no reason for the other three; remove the
     option and round_div's parameter.

  5. cache.py: ToolCache with a TTL. The CLI is a one-shot process (R1), and the
     spec doesn't mention caching, so this is dead weight.

OK AS WRITTEN

  - the notice retry: 3 attempts, 1 s apart (R11)
  - --format csv (R9)
  - fines, caps, discount rounding (R7)
