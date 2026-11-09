# Safe updates and verification

## Identity and preservation

Capture a baseline of the scoped native records, with a recoverable raw export where possible. Keep backup data private and outside public repositories or share services. Confirm the backup is parseable and includes the fields needed to restore the records. Record the original map selection and relevant visibility settings.

Use stable collection/marker identity or an explicit crosswalk to native IDs. If identity is unavailable, compare geometry, coordinates, floor, category, and name as evidence; surface ambiguity instead of making proximity the identity. Two destinations at one coordinate, or matching x/y on different floors, can both be valid.

Classify the proposed operation as additions, exact duplicates, requested field updates, ambiguous matches, and explicitly authorized deletions. Merge preserves unrelated markers and unrequested fields. Repeated identical imports are a no-op; restyling is a field update, not remove-and-recreate. User edits made since the last import are preserved or shown as conflicts.

## Applying a change

Prepare the full mutation plan before writing. Show the collection, number of affected records, fields changed, and unsupported or lost fields. The user's setup request covers its ordinary additive edits; destructive replacement, clearing unrelated data, publishing private details, or installing additional software requires separate authority.

Keep the baseline and intended result outside the active store while applying. If the storage surface supports atomic transactions, use them. Otherwise use a recoverable staged operation and detect partial completion. Recheck the scoped baseline immediately before writing so edits from another tab are not overwritten.

A fallback helper checks the observed schema and origin before it reaches its write path. An unexpected layout, quota error, stale baseline, or inaccessible store stops the mutation and identifies the affected step. It neither guesses another storage key nor reports partial writes as success.

Verify stored results immediately. A rollback removes or restores only the operation's own changes. Restore an old field only when its current value still equals what the operation wrote; otherwise preserve the intervening edit and report the conflict. A broad storage reset is not a rollback.

## Acceptance evidence

Check against the expected collection, not just a successful return value:

| Boundary | Evidence |
| --- | --- |
| Prepared collection | Exact unique identities, category/floor totals, finite coordinates, source notes and style mapping. |
| Conversion | Decoder round-trip preserves every supported field; any loss is explicitly documented. |
| Import | Target application accepts a representative multi-marker case, then reconciles the full count and identities. |
| Appearance | Each distinct native icon/style renders on the actual map with the expected label and group behavior. |
| Search and floors | Representative names and categories can be found with the intended floor and filters. |
| Persistence | Reload retains records and style; an export agrees with the intended native values. |
| Sharing | A separate browser context imports the link without relying on the author's local cache or icon files. |
| Rerun | Reapplying makes no duplicate points and preserves unrelated and individually edited markers. |
| Recovery | Backup can restore an isolated test change; partial failure and concurrent edits do not discard user data. |

Use a disposable browser profile for destructive and malformed-input tests. Include varied categories and floors, missing/unsupported symbols, duplicate imports, existing personal markers, Unicode, large collections, and at least one negative case that the validation must reject. Bound decoding and record sizes; map labels and descriptions render as plain data.

An offline unit test or export inspection does not prove a live import, and a screenshot does not prove persistence. Record test scope and unavailable boundaries in the task delivery. Comparative agent trials assess the instructions themselves; browser acceptance checks assess the setup the agent produced.

## User-facing handoff

Provide one primary artifact or launch path suited to the user's browser, with only the steps actually verified. Explain whether opening it changes markers immediately, requests confirmation, or merely previews data. Include an icon/category legend, collection scope, supported map selection, field losses, and the backup/undo method.

Keep a lossless source collection and a readable fallback with coordinates and floors. Mark overlapping subset files so users do not mistake them for extra records that all need importing. A link that exceeds the delivery channel's limits is not a working single-click import.

Useful final wording distinguishes “prepared”, “accepted by the live importer”, “rendered”, “persisted after reload”, and “shared-context verified”. Name any missing evidence without upgrading it to success. Verification receipts, timestamps, hashes, and per-user setup data belong in the task's artifacts or private working records; they are not maintained plugin instructions.
