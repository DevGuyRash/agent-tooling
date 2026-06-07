# Verification Loop

A proposed fix is incomplete until the agent can tell whether it worked and how
to recover when it did not.

## Success Definition

You SHALL define what success looks like before listing edits.
You SHALL include a verification plan in every Improvement Brief.
WHEN the recommendation changes metadata THEN you SHALL rerun the trigger eval
set.
WHEN the recommendation changes workflow or structure THEN you SHALL rerun at
least one representative task.

## Recovery Loop

Use a simple loop:

1. Make the smallest change that addresses the leading failure.
2. Re-run the most relevant eval or task.
3. Compare before and after.
4. Keep the change only if the evidence improved.

WHEN the first fix does not improve the result THEN you SHALL record the failed
assumption and you SHALL try the next highest-leverage change.
WHEN deterministic scripts exist THEN you MAY use them for structural evidence,
but you SHALL NOT substitute them for behavioral verification.

## Minimal Regression Set

Every verification plan should usually cover:

- one trigger or packaging check tied to the changed boundary
- one representative task tied to the changed workflow
- one structural check tied to the changed files

## Deliverables

You SHALL state the exact checks to rerun.
You SHALL state what result would count as success.
You SHALL state what to try next if the result does not improve.
