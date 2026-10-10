# GoalSpec Examples

These examples show the decision behavior, not a template. Copy the judgment: explore before capturing, write durable docs after convergence, and use probes before execution.

## Example: Vague Design Prompt

Raw user prompt:

> Make imports less painful for customers.

Good output:

```md
## Option Map

Source signals:
- "less painful" is broad; the pain could be correctness, diagnosis, tolerance, or workflow.
- "customers" suggests user-facing failure recovery matters, not only internal parser quality.

Directions:
1. Correctness first: fix known parsing failures so valid files import reliably. Optimizes for trust; may not help users understand bad rows.
2. Diagnostics first: improve row-level error messages and recovery. Optimizes for user confidence; may leave some valid messy files unsupported.
3. Tolerance first: accept more messy real-world CSV variants. Optimizes for convenience; risks ambiguous parsing rules.

Recommendation:
- Start with diagnostics if the user pain is support burden or confusion.
- Start with correctness if there is a named broken case.

Decision needed:
- Are customers mainly blocked by valid files importing incorrectly, or by not understanding rejected rows?
```

Why this works:

- It treats ambiguity as a design phase.
- It offers real product directions, not document types.
- Do not write `context/docs/` before the user chooses a direction.

## Example: Known Bugfix Probe Note

Raw user prompt:

> The contact CSV import is flaky. It basically works, but quoted mailing addresses with commas split wrong. Don't replace the importer or introduce pandas.

Good output:

```md
## Probe Note

Intent delta:
- This is a targeted parsing correctness fix, not an importer rewrite.
- "Basically works" means existing simple imports must stay compatible.
- "Don't introduce pandas" excludes third-party dependency expansion.

Acceptance probes:
- `Ada,ada@example.com,"123 Main St, Apt 4"` produces one `address` value: `123 Main St, Apt 4`.
- `Bob,bob@example.com,Paris` still produces the same dict as before.
- The public import function still accepts text and returns `list[dict]`.

Non-goals:
- No new import workflow.
- No third-party package dependency.

Executor freedom:
- Any implementation is acceptable if it passes the probes and preserves the public surface.

Final review:
- Re-read the request and confirm the importer was not replaced, pandas was not added, and the quoted-comma case is covered by a test or equivalent check.
```

Why this works:

- It does not create a durable planning file for a small known change.
- It avoids implementation HOW while making the bad product easy to catch.

## Example: PRD Option Map

PRD excerpt:

> Empty recipe results return a recovery suggestion that points the cook back to browsing saved recipes.
>
> Existing callers can continue using `search_recipes(recipes, query)`.

Good output before convergence:

```md
## Option Map

Source signals:
- Empty results need a recovery suggestion.
- Existing two-argument callers must keep working.
- Existing callers may iterate the returned value as a list of recipe dicts.

Directions:
1. Metadata-bearing list: return a list-like result with a `.suggestion` attribute. Optimizes for compatibility; adds a small custom type.
2. Sentinel item in list: return `[{"suggestion": "..."}]`. Optimizes for simplicity; risks fake recipe objects breaking callers.
3. New result object: return `{matches, suggestion}`. Optimizes for clarity; likely breaks existing list callers.

Recommendation:
- Prefer metadata-bearing list because it satisfies the empty-state requirement while preserving list iteration for existing callers.

Safe default:
- Proceed with metadata-bearing list and document the choice.
```

Why this works:

- It does not block on an executor-owned API design choice.
- It recommends the product-compatible default and names the probes that should bound it.

## Example: Post-Convergence Decision Capture

User accepts:

> Let's use the metadata-bearing list for recipe search. Keep the MVP small.

Good durable update:

```md
Update or create `context/docs/recipe-search-decision.md` because the direction is now chosen and affects future callers.

Capture:
- Chosen direction: list-like search result with suggestion metadata.
- Rejected alternatives: sentinel dict and non-list result object.
- Rationale: preserves existing iteration while satisfying empty-state recovery.
- Probe Pack: exact-before-partial ranking, meal-type filter, empty suggestion metadata, existing two-argument call still works.
- Non-goals: no OCR, no photo import, no web UI.
```

Why this works:

- The file appears after convergence.
- It preserves rejected alternatives and rationale, not just the final answer.

## Example: Ready-To-Build Probe Pack

Good handoff after direction is chosen:

```md
## Probe Pack

Source anchors:
- AC1: exact title matches rank before partial title matches.
- AC2: results can be filtered by meal type.
- AC3: empty results return a recovery suggestion.
- Invariant: existing two-argument calls keep working.

Acceptance probes:
- Query `soup` over `Soup`, `Tomato Soup`, and `Soup Dumplings`; `Soup` ranks first.
- Query `soup` with `meal_type=lunch`; only lunch matches remain.
- Query `zzzz`; result exposes a recovery suggestion.

Compatibility probes:
- Existing code can still iterate non-empty results and access `recipe["title"]`.
- `search_recipes(recipes, query)` still works without a third argument.

Executor-owned design:
- Internal sorting and data structures are free.
- Empty-result metadata shape is fixed by the accepted direction.

Final source review:
- Confirm each PRD acceptance criterion is represented by a check.
- Confirm OCR, photo import, and web UI stayed out of scope.
```

Why this works:

- It makes final product quality easier to evaluate.
- It constrains outcomes without prescribing implementation steps.
