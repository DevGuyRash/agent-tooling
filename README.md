# Agent Skills

This repository contains portable Agent Skills (AgentSkills open standard).

## Skills

### `perform-code-review`

Perform adversarial code reviews using the UACRP protocol and report template, writing coordination artifacts under `.local/reports/code_reviews/{YYYY-MM-DD}/` and using a bundled `mpcr` tool for deterministic reviewer/session operations (ID generation, locking, session JSON updates, report writing).

Path: `skills/perform-code-review/`

### `apply-code-review`

Apply code review feedback by consuming completed review reports and updating coordination state (`initiator_status`, applicator notes) in `.local/reports/code_reviews/{YYYY-MM-DD}/_session.json`, using a bundled `mpcr` tool for deterministic waiting, session inspection, status updates, and notes.

Path: `skills/apply-code-review/`

