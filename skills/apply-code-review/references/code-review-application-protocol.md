# Code Review Application Protocol

**Status:** Canonical baseline
**Role:** Feedback Applicator (NOT a reviewer)
**Core philosophy:** Reviewers create entries; you consume them and update your progress on their entries.
**Primary objective:** Read completed reviews, apply feedback systematically, and track your progress via `initiator_status`.

---

## I) Your role

You are the applicator of code review feedback. Your mission is to make the code better by fixing the issues identified in reviews. Each finding points to a problem—your job is to make that problem go away.

**Success:** Every actionable finding is either fixed in the code or explicitly declined with justification. Coordination artifacts track this work—they are not the work itself.

**You are NOT a reviewer.** You SHALL NOT add yourself to the `reviewers` array. You SHALL NOT add entries to the `reviews` array. Reviewers create those entries; you update the `initiator_status` field on their existing entries.

---

## II) Session file (`_session.json`)

All review coordination occurs through a shared session file.

### Storage location

```bash
{repo_root}/.local/reports/code_reviews/{YYYY-MM-DD}/
├── _session.json
├── _session.json.lock
└── {HH-MM-SS-mmm}_{ref}_{reviewer_id}.md
```

### Schema

```json
{
  "schema_version": "1.0.0",
  "session_date": "{YYYY-MM-DD}",
  "repo_root": "{absolute_path}",
  "reviewers": ["{reviewer_id}", ...],
  "reviews": [
    {
      "reviewer_id": "{8_char_id}",
      "session_id": "{8_char_id}",
      "target_ref": "{branch_or_pr_ref}",
      "initiator_status": "{INITIATOR_STATUS}",
      "status": "{REVIEWER_STATUS}",
      "parent_id": "{parent_reviewer_id_or_null}",
      "started_at": "{ISO8601_timestamp}",
      "updated_at": "{ISO8601_timestamp}",
      "finished_at": "{ISO8601_timestamp_or_null}",
      "current_phase": "{PHASE_or_null}",
      "verdict": "{APPROVE|REQUEST_CHANGES|BLOCK|null}",
      "counts": { "blocker": 0, "major": 0, "minor": 0, "nit": 0 },
      "report_file": "{filename_or_null}",
      "notes": []
    }
  ]
}
```

---

## III) Status values

### Your status (`initiator_status`)

You own and update this field. Reviewers observe it but SHALL NOT modify it.

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

Reviewers own this field. You observe it but SHALL NOT modify it.

| Status         | Meaning                                      |
| -------------- | -------------------------------------------- |
| `INITIALIZING` | Registered; review not yet started           |
| `IN_PROGRESS`  | Actively reviewing                           |
| `FINISHED`     | Completed with verdict and counts            |
| `CANCELLED`    | Stopped before completion                    |
| `ERROR`        | Encountered fatal error; see notes           |
| `BLOCKED`      | Awaiting external dependency or intervention |

---

## IV) Lock acquisition protocol

You SHALL generate an 8-character alphanumeric identifier and use it as your lock owner (NOT `$$`) because acquire and release may occur in different processes.

### Random value generation

WHEN you need to generate random identifiers (your_id, lock_owner, or any other random values) THEN you SHALL use `mpcr`:

- `mpcr id hex --bytes 4` (8 chars) for `your_id` and lock owners.
- For different identifier lengths, adjust `--bytes` (2N hex characters).

You SHALL NOT read directly from `/dev/urandom` or `/dev/random` as this can cause memory exhaustion and system freezes.

### Acquire lock

Use:

- `mpcr lock acquire --session-dir "${session_dir}" --owner "${your_id}" --max-retries 8`

### Atomic write (while lock held)

Use `mpcr` applicator commands (they update `_session.json` via temp file + replace):

- Temp file: `{session_dir}/_session.json.tmp.{lock_owner}`
- Replace: `{session_dir}/_session.json`

### Release lock

Use:

- `mpcr lock release --session-dir "${session_dir}" --owner "${your_id}"`

Backoff sequence: 100ms → 200ms → 400ms → 800ms → 1600ms → 3200ms → 6400ms → 6400ms (cap).

---

## V) Coordination rules

### What you own

- `initiator_status`: You SHALL update this field **on existing review entries** to reflect your progress consuming that review
- `notes`: You MAY append notes with `role: "applicator"` to communicate decisions back to reviewers
- Session creation: You MAY create the session directory and `_session.json` if they do not exist (before reviewers start)

### What you SHALL NOT do

- You SHALL NOT add yourself to the `reviewers` array
- You SHALL NOT create new entries in the `reviews` array
- You SHALL NOT modify `status`, `verdict`, `counts`, `report_file`, or other reviewer-owned fields

### What you observe

- `status`: Each reviewer's progress
- `verdict`: Each reviewer's final decision
- `counts`: Blocker/major/minor/nit tallies
- `report_file`: Path to the reviewer's full report (you SHALL read this file)
- `notes`: Structured observations from reviewers (look for `role: "reviewer"`)

### Notes array

The `notes` array enables bidirectional communication. Each note has a `role` indicating who wrote it.

```json
{
  "role": "{reviewer|applicator}",
  "timestamp": "{ISO8601}",
  "type": "{note_type}",
  "content": "{free_form_or_structured}"
}
```

#### Your note types (`role: "applicator"`)

| Type                   | Purpose                               |
| ---------------------- | ------------------------------------- |
| `applied`              | Confirmed feedback was applied        |
| `declined`             | Feedback was not applied, with reason |
| `deferred`             | Will address later (include tracking) |
| `already_addressed`    | Already handled elsewhere (reference) |
| `acknowledged`         | Read and understood, no action needed |
| `clarification_needed` | Requesting more detail from reviewer  |

#### Reviewer note types (for your awareness)

| Type                 | Purpose                               |
| -------------------- | ------------------------------------- |
| `escalation_trigger` | Flagging high-risk area for attention |
| `domain_observation` | Insight about a specific domain       |
| `blocker_preview`    | Early warning of potential blocker    |
| `question`           | Requesting clarification from you     |
| `handoff`            | Context for another reviewer          |
| `error_detail`       | Details about an error encountered    |

WHEN you observe reviewer notes with `type: "question"` THEN you SHALL append a response note.

### Session lifecycle

1. **Request:** You set `initiator_status` to `REQUESTING`
2. **Observe:** As reviewers register and work, you MAY update to `OBSERVING`
3. **Receive:** When reviewers reach `FINISHED`, you update to `RECEIVED`
4. **Review:** After reading and assessing feedback, you update to `REVIEWED`
5. **Apply:** While applying feedback you chose to accept, you update to `APPLYING`
6. **Complete:** When done processing (applied, declined, or deferred), you update to `APPLIED`
7. **Cancel:** If abandoning, you update to `CANCELLED`

---

## VI) Reading reviews

WHEN any reviewer's `status` is `INITIALIZING`, `IN_PROGRESS`, or `BLOCKED` THEN you SHALL wait until all reviewers reach a terminal status.

Use:

- `mpcr applicator wait --session-dir "${session_dir}"`

FOR EACH review entry WHERE `status` is `FINISHED` AND `initiator_status` is `REQUESTING` or `OBSERVING`:

1. You SHALL read the full report file at `{session_dir}/{report_file}`
2. You SHALL update `initiator_status` to `RECEIVED` on that entry after reading
3. You SHALL analyze the `verdict`, `counts`, and report contents to understand the feedback

You SHALL NOT skip reading `report_file`. The session file metadata (`counts`, `verdict`) is a summary only; the full report contains the actionable findings.

The findings contain anchors pointing to specific code locations. Those anchors are your entry points for fixes.

---

## VII) Processing feedback

FOR EACH finding in a reviewer's report:

1. Read the code at the anchor location
2. Understand the problem described
3. Fix it—or decide not to and document why

You are not required to apply all feedback, but you SHALL address each finding. Document your decision via a note with `role: "applicator"`:

- `type: "applied"` — You applied the feedback (include what you changed)
- `type: "declined"` — You chose not to apply (you SHALL explain why in `content`)
- `type: "deferred"` — You will address later (include tracking info if applicable)
- `type: "already_addressed"` — Already handled elsewhere (reference where)
- `type: "acknowledged"` — No action needed (explain why)

FOR EACH review entry you are processing:

1. You SHALL update `initiator_status` to `REVIEWED` after reading and assessing
2. You SHALL update `initiator_status` to `APPLYING` while making changes
3. You SHALL update `initiator_status` to `APPLIED` when done processing that review

You SHALL respect the lock protocol when updating session state.

WHEN all review entries have `initiator_status` of `APPLIED` or `CANCELLED` THEN your work is complete.

