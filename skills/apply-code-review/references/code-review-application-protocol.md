# Code Review Application Protocol

**Status:** Canonical baseline
**Role:** Feedback Applicator (NOT a reviewer)
**Core philosophy:** Reviewers create entries; you consume them and update your progress on their entries.
**Primary objective:** Read completed reviews, apply feedback systematically, and track your progress via `initiator_status`.

---

## Deliverables (at a glance)

- You SHALL read each review report AND the code files it references to verify findings against actual code.
- You SHALL decide whether to fix, decline, or defer each finding based on your own assessment—not blind acceptance.
- You SHALL record a disposition for every finding: applied, declined, deferred, already addressed, or acknowledged (with reasoning).
- You SHALL keep progress visible to reviewers via `initiator_status` and applicator notes.
- IF a reviewer asks a question (note type `question`) THEN you SHALL respond via an applicator note.

---

## I) Your role

You are the applicator of code review feedback. Your mission is to make the code better by fixing the issues identified in reviews. Each finding points to a problem—your job is to make that problem go away.

**Success:** Every actionable finding is either fixed in the code or explicitly declined with justification. Coordination artifacts track this work—they are not the work itself.

**You are NOT a reviewer.** You SHALL NOT add yourself to the `reviewers` array. You SHALL NOT create entries in the `reviews` array. Reviewers create those; you SHALL update the `initiator_status` field on their existing entries.

---

## II) Status values

### Your status (`initiator_status`)

You own this field. You SHALL update it via `mpcr applicator set-status`. Reviewers observe it but SHALL NOT modify it.

| Status       | Meaning                                          |
| ------------ | ------------------------------------------------ |
| `REQUESTING` | Review requested; waiting for reviewers          |
| `OBSERVING`  | Watching reviews in progress                     |
| `RECEIVED`   | Has received completed reviews                   |
| `REVIEWED`   | Has read and assessed feedback; deciding actions |
| `APPLYING`   | Actively applying accepted feedback              |
| `APPLIED`    | Finished processing feedback (applied/declined)  |
| `CANCELLED`  | You cancelled the request                        |

### Reviewer status (`status`)

Reviewers own this field. You SHALL observe it but SHALL NOT modify it.

| Status         | Meaning                                      |
| -------------- | -------------------------------------------- |
| `INITIALIZING` | Registered; review not yet started           |
| `IN_PROGRESS`  | Actively reviewing                           |
| `FINISHED`     | Completed with verdict and counts            |
| `CANCELLED`    | Stopped before completion                    |
| `ERROR`        | Encountered fatal error; see notes           |
| `BLOCKED`      | Awaiting external dependency or intervention |

---

## III) Notes

Notes enable bidirectional communication. You SHALL use `mpcr applicator note` to append yours.

You SHALL treat notes as append-only; duplicates MAY exist. WHEN you create a note THEN you SHALL make it unambiguous and auditable on its own.

### Your note types (`role: "applicator"`)

| Type                   | Purpose                               |
| ---------------------- | ------------------------------------- |
| `applied`              | Confirmed feedback was applied        |
| `declined`             | Feedback was not applied, with reason |
| `deferred`             | Will address later (include tracking) |
| `already_addressed`    | Already handled elsewhere (reference) |
| `acknowledged`         | Read and understood, no action needed |
| `clarification_needed` | Requesting more detail from reviewer  |

### Reviewer note types (for your awareness)

| Type                 | Purpose                               |
| -------------------- | ------------------------------------- |
| `escalation_trigger` | Flagging high-risk area for attention |
| `domain_observation` | Insight about a specific domain       |
| `blocker_preview`    | Early warning of potential blocker    |
| `question`           | Requesting clarification from you     |
| `handoff`            | Context for another reviewer          |
| `error_detail`       | Details about an error encountered    |

WHEN a reviewer posts a `question` note THEN you SHALL respond via `mpcr applicator note`.

---

## IV) Reading reviews

`mpcr` defaults `--repo-root` to the current working directory; session directory derives from repo root and date. Omit these flags only when running from the target repository's root.

You SHALL wait for reviewers with non-terminal `status` (`INITIALIZING`, `IN_PROGRESS`, or `BLOCKED`) to complete before processing. Use `mpcr applicator wait` to block until all reviewers reach terminal status.

You SHALL fetch completed reviews you haven't processed yet:

```
mpcr session reports closed --initiator-status REQUESTING,OBSERVING --include-report-contents --json
```

The `report_contents` field contains the full markdown with actionable findings and code anchors. You SHALL run `mpcr session reports closed --help` for all available filters.

Every actionable issue in `report_contents` is a finding requiring an explicit disposition. Use UACRP finding headings and anchors for systematic tracking.

FOR EACH review, you SHALL analyze the `verdict`, `counts`, and report contents to understand the feedback, then you SHALL update `initiator_status` to `RECEIVED`.

---

## V) Processing feedback

FOR EACH finding in a reviewer's report, you SHALL:

1. Read the code at the anchor location
2. Understand the problem described
3. Fix it—or decide not to and record a disposition (applied/declined/deferred/already_addressed/acknowledged) with justification.

You are not required to apply all feedback, but you SHALL address each finding. You SHALL document each disposition and your decision via `mpcr applicator note`:

- `type: "applied"` — You applied the feedback (include what you changed)
- `type: "declined"` — You chose not to apply (you SHALL explain why in content)
- `type: "deferred"` — You will address later (include tracking info if applicable)
- `type: "already_addressed"` — Already handled elsewhere (reference where)
- `type: "acknowledged"` — No action needed (explain why)

Notes attach to the review entry (not to individual findings). Record **one note per finding** so each disposition is traceable. Identify each finding using the format: `{SEVERITY}: {short title}` with code anchor `{file}:{lines}`.

### Disposition note format

Use `--content-json` for structured tracking. Required fields:

| Field         | Required | Description                                                                    |
| ------------- | -------- | ------------------------------------------------------------------------------ |
| `finding_ref` | Yes      | Finding identifier: `"{SEVERITY}: {short title}"`                              |
| `anchor`      | Yes      | Code location: `"{file}:{line}"` or `"{file}:{start}-{end}"`                   |
| `disposition` | Yes      | One of: `applied`, `declined`, `deferred`, `already_addressed`, `acknowledged` |
| `summary`     | Yes      | What you did or why you chose this disposition                                 |

Optional fields: `changes` (files/lines modified), `tracking` (issue URL for deferred items), `notes` (additional context).

**Example:**
```bash
mpcr applicator note --session-id SESSION_ID --reviewer-id REVIEWER_ID \
  --note-type applied \
  --content-json --content '{
    "finding_ref": "BLOCKER: SQL injection in verify_user()",
    "anchor": "auth.py:21-22",
    "disposition": "applied",
    "summary": "Replaced f-string with parameterized query using ? placeholders"
  }'
```

`SESSION_ID` and `REVIEWER_ID` come from the JSON output of `mpcr session reports`.

IF you have set `MPCR_SESSION_ID` and `MPCR_REVIEWER_ID` in your environment for the current review entry THEN you MAY omit `--session-id/--reviewer-id` flags in `mpcr` commands.

### Status progression

You SHALL update your status as you work:

1. `RECEIVED` — after you read and understand the review
2. `REVIEWED` — after you assess all findings and decide what to do
3. `APPLYING` — while you make changes to the code
4. `APPLIED` — when you finish processing that review

`APPLIED` requires an explicit disposition recorded for every finding in that review. For partial completion, you SHALL remain at `APPLYING` and use notes to communicate progress.

WHEN there are multiple reviewers, you SHALL process each review independently. You SHALL set `APPLIED` after completing each review's findings—you SHALL NOT wait to set `APPLIED` until after all reviews are completed, instead YOU SHALL asynchronously process each review.
