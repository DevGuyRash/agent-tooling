# Small-Batch Patterns

Read this reference when the current change cannot safely integrate as one coherent short-lived increment. Select patterns from constraints.

## Vertical slices

Deliver one narrow path through the stack, including its test and observability, instead of completing every data-layer change before any usable behavior. Use a vertical slice when it can be independently exercised without creating a second unfinished architecture.

## Compatible additions first

Land additive types, endpoints, fields, adapters, or internal seams before their consumers. Such an addition is exercised in the same increment or has a clear near-term consumer; avoid speculative frameworks and unused abstractions.

Keep old consumers working until the dependent slice is integrated. Remove the old path in a later increment, once usage evidence shows it is idle.

## Branch by abstraction

Introduce a stable internal seam around the component being replaced, route the current implementation through it, add the new implementation behind the seam, switch consumers, then remove the old implementation and transitional seam once unused. Each state should build and preserve normal trunk behavior.

Use this for structural replacements whose implementations must coexist. Do not introduce a broad abstraction when a direct compatible edit can integrate safely.

## Feature flags and inactive paths

Separate code integration from user exposure when runtime behavior would be incomplete or risky. Define the default state, eligible environments or cohorts, observability, fail-safe behavior, expiry, and removal condition.

Flags add state combinations and operational cost. Avoid nested or permanent flags, and do not use a flag to bypass required compatibility or correctness.

## Stacked changes

Use ordered dependent changes when each is independently understandable but cannot yet target trunk directly. Make dependency edges visible, update later changes when an earlier one changes, and integrate in order. Prefer compatibility seams when stacking would keep the effective branch lifetime long.

## Refactor, then behavior

Land a behavior-neutral preparatory refactor with preservation evidence before the feature or bugfix when combining them would obscure review or rollback. Small local cleanup may remain with the behavior change when separation costs more than it clarifies.

## Migration slices

Typical safe increments are expand, introduce compatibility handling, backfill or shadow, shift consumers, verify, contract, and remove transitional machinery. Use the phases and consistency controls the migration needs, each as an independently integrable change.

## Evaluate a proposed slice

Check whether trunk remains healthy if later slices never arrive, whether deployed old and new versions can coexist as required, whether the slice has meaningful verification, and which revert, containment, or forward-repair path remains valid after dependent slices integrate. If no safe recovery path is visible, split differently or make the dependency and compatibility mechanism explicit.
