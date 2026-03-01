# Rules

The auditor MUST record every finding with confidence and anchor evidence.
The auditor MUST NOT record every finding with confidence and anchor evidence.

You SHALL keep the duplication pass deterministic and byte-stable across
repeated runs for unchanged input files and sorting order.
You SHALL sort scanned files before comparing directives or normalized
instruction blocks to avoid ordering drift in findings.
You SHALL separate operative duplicates from advisory duplicates in the
final report so verdict gating only reflects operative files.
