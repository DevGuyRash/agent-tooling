# feature/overdue-notices vs SPEC.md

| # | Severity | Where | Finding | Action |
|---|----------|-------|---------|--------|
| 1 | High | toolroom/overdue.py:21 | R8 wants loans with the same days ordered by member name A-Z, then loan id. `reverse=True` on the whole key lists ties Z-A and loan ids descending. | Sort on `(-days, member, loan)`; add a tie test |
| 2 | High | toolroom/notices.py:15 | R10: the notice total is the sum of the fines shown. `total_owed` recomputes days x 50, so it ignores the cap (R7) and the supporter discount. | Sum `row.fine` |
| 3 | Low | toolroom/rules.py | Abstract `FineRule` + `RULES` registry + `register` / `get_rule` for one rule. Not required by any SPEC line; YAGNI. | Remove; call the per-day computation directly |
| 4 | Low | toolroom/cli.py:29, toolroom/fines.py:4 | `--rounding` offers nearest / up / down / even; R7 specifies only nearest, halves up. Extra surface nobody asked for. | Drop the option and the other modes |
| 5 | Low | toolroom/cache.py | `ToolCache` (TTL 300 s) in a run-once CLI. SPEC never mentions caching. | Could be dropped; pass the loaded tools instead |
| 6 | Info | toolroom/notices.py:25-35, toolroom/cli.py:27 | The retry (3 attempts, 1 s apart) and `--format csv` look like extras but are required by R11 and R9. | None |

33 tests pass; none of them has two loans with the same days or a capped or discounted notice.
