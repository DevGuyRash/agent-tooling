---
name: tiered-demo
description: >-
  Fixture skill for deterministic duplication testing. Use when validating
  operative versus advisory duplication handling and contradiction detection.
---

# Tiered Demo

Read `<skills-file-root>/references/rules.md` and
`<skills-file-root>/references/bridge.md` before finalizing the audit.

The auditor MUST record every finding with confidence and anchor evidence.

You SHALL keep the duplication pass deterministic and byte-stable across
repeated runs for unchanged input files and sorting order.
You SHALL sort scanned files before comparing directives or normalized
instruction blocks to avoid ordering drift in findings.
You SHALL separate operative duplicates from advisory duplicates in the
final report so verdict gating only reflects operative files.
