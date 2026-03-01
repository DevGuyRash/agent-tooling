# Confidence Scoring Framework

Severity alone does not determine how actionable a finding is — confidence in
the evidence behind it matters equally. This framework assigns a confidence
level to every finding so that reviewers can triage effectively and avoid
blocking on uncertain results.

---

## Confidence Levels

| Level  | Tag   | Definition |
|--------|-------|------------|
| HIGH   | `[H]` | Verified deterministically — script output, exact CLI error, or measurable threshold breach provides objective proof. |
| MEDIUM | `[M]` | Verified by agent inspection — the agent traced the code path, read the file, and confirmed the pattern with contextual evidence. |
| LOW    | `[L]` | Inferred from pattern matching — the agent recognized a known anti-pattern but did not fully trace execution or data flow. |

---

## Assignment Rules

WHEN a finding is produced by a deterministic script,
THEN confidence SHALL be HIGH.

WHEN a finding is produced by agent inspection with traced evidence,
THEN confidence SHALL be MEDIUM.

WHEN a finding is produced by pattern recognition without a full trace,
THEN confidence SHALL be LOW.

IF a finding has LOW confidence,
THEN the auditor SHALL note what additional verification would raise it
(e.g., "run integration tests", "trace call-site in module X").

---

## Confidence in the Report

Each finding SHALL include a `Confidence:` line immediately after severity:

```
### F-<ID>: <title>
- **Severity:** BLOCKER | MAJOR | MINOR | NIT
- **Confidence:** HIGH [H] | MEDIUM [M] | LOW [L]
- **Location:** <file>:<line>
- **Evidence:** <what was observed>
- **Recommendation:** <actionable fix>
```

The executive summary SHALL include a confidence distribution:

```
**Confidence Distribution:** H:<count> · M:<count> · L:<count>
```

---

## Confidence-Gated Verdicts

WHEN a BLOCKER finding has HIGH confidence,
THEN the verdict SHALL be a hard block with no override.

WHEN a BLOCKER finding has LOW confidence,
THEN the verdict SHALL block WITH the note: "verify before shipping."

IF a MAJOR finding has LOW confidence,
THEN it SHALL NOT count toward the SHIP_WITH_FIXES threshold
UNLESS the auditor provides a concrete path to raise confidence
(e.g., specifying a script to run or a code path to trace).

---

## Per-Phase Confidence Requirements

Each audit phase has different confidence characteristics based on the
verification methods available.

| Phase | Typical Confidence | Rationale |
|-------|--------------------|-----------|
| 1 — Environment & Build | HIGH | Script-verified: CRLF, permissions, shebangs, build status |
| 2 — API Surface | HIGH–MEDIUM | Script-verified for name checks; agent-verified for error quality |
| 3 — Workflow Simulation | MEDIUM | Agent walks through workflow; evidence is contextual |
| 3b — Multi-Agent | MEDIUM | Cross-role measurement is HIGH; prompt quality assessment is MEDIUM |
| 4 — Context & Token | HIGH | Script-measured character counts and context sizing |
| 4b — Duplication Gate | HIGH | Exact duplicate and contradiction matching are deterministic |
| 5 — Output Quality | MEDIUM–LOW | Template evaluation and anti-laziness checks are agent-inferred |

WHEN a phase produces only HIGH-confidence findings, THEN the phase's
findings SHALL carry full weight in the final verdict.

WHEN a phase produces mostly LOW-confidence findings, THEN the auditor
SHALL note what additional verification would raise confidence before
those findings can gate a verdict.

---

## Per-Domain Confidence Rules

Each domain (D1–D22) has a designated confidence tier that reflects its
primary verification method.

| Tier | Domains | Default Confidence |
|------|---------|-------------------|
| Deterministic | D1, D2, D4, D11, D16, D17 | HIGH — script output is objective proof |
| Heuristic+Script | D3, D14, D15 | HIGH for script metrics, MEDIUM for interpretation |
| Agent+Script | D5, D7, D8, D10, D12, D21, D22 | MEDIUM — agent verifies with CLI or inspection evidence |
| Agent-only | D6, D9, D13, D18, D19, D20 | MEDIUM for traced evidence, LOW for pattern-matched |

WHEN a domain's script produces output, THEN the finding confidence
SHALL be at least MEDIUM, regardless of the domain's tier.

WHEN a domain relies solely on agent inspection without script backing,
THEN the finding confidence SHALL NOT exceed MEDIUM unless the agent
provides exact file:line evidence and quotes the relevant text.

WHEN D16 findings are produced by `duplication_check.sh` using exact
duplicate/contradiction matches, THEN confidence SHALL be HIGH [H]
throughout the report and in gate decisions.

---

## Convergence Confidence (D18)

Convergence findings measure audit reproducibility. Their confidence
follows special rules:

WHEN a convergence finding is backed by running the same script twice and
comparing output, THEN confidence SHALL be HIGH.

WHEN a convergence finding is based on comparing two agent audit passes,
THEN confidence SHALL be MEDIUM (agents may phrase findings differently).

WHEN a convergence finding is based on theoretical analysis ("this rubric
is ambiguous and would likely produce different results"), THEN confidence
SHALL be LOW.

---

## Divergence Confidence (D19)

Divergence findings measure output specificity. Their confidence follows
special rules:

WHEN a divergence finding is backed by text comparison (e.g., >60% verbatim
overlap between two audit reports), THEN confidence SHALL be HIGH.

WHEN a divergence finding is based on agent assessment of recommendation
quality ("this recommendation is generic"), THEN confidence SHALL be MEDIUM.

---

## Adherence Confidence (D20)

Adherence findings measure rule absorption. Their confidence follows
special rules:

WHEN an adherence finding is backed by script verification (e.g., EARS
check confirms missing SHALL keywords), THEN confidence SHALL be HIGH.

WHEN an adherence finding is based on agent inspection of AGENTS.md
rule coverage ("this AGENTS.md section has no corresponding audit check"),
THEN confidence SHALL be MEDIUM.

WHEN an adherence finding is based on structural assessment ("the skill's
progressive disclosure model doesn't match the AGENTS.md pattern"),
THEN confidence SHALL be MEDIUM only IF the agent provides specific
file structure evidence.

---

## Staleness Confidence (D21)

Staleness findings measure documentation/runtime drift. Their confidence
follows special rules:

WHEN a staleness finding is backed by deterministic script evidence
(`staleness_check.sh` example transcript, missing script path, or unknown
flag detection), THEN confidence SHALL be HIGH.

WHEN a staleness finding is based on agent comparison between nearby prose
claims and a captured execution transcript, THEN confidence SHALL be MEDIUM.

WHEN a staleness finding is inferred without executing any documented example
or collecting a transcript, THEN confidence SHALL be LOW.

---

## Discoverability Confidence (D22)

Discoverability findings measure one-step recovery affordances for enum-like
CLI parameters.

WHEN a discoverability finding is backed by deterministic script evidence
(`discoverability_check.sh` helper counts, option coverage misses, CLI help
probe output), THEN confidence SHALL be HIGH.

WHEN a discoverability finding is based on agent interpretation of helper
wording clarity, THEN confidence SHALL be MEDIUM.

WHEN a discoverability finding is inferred without CLI help evidence or
documented helper extraction, THEN confidence SHALL be LOW.

## Aggregate Confidence Score

The aggregate confidence score quantifies overall evidence quality:

```
score = (HIGH_count × 3 + MEDIUM_count × 2 + LOW_count × 1) / (total_findings × 3)
```

WHEN computing the aggregate score, D18/D19/D20/D21/D22 findings SHALL be
included in the calculation alongside D1–D17 findings. Their confidence levels follow
the same HIGH=3, MEDIUM=2, LOW=1 weighting.

### Interpretation Bands

| Band               | Score   | Meaning |
|--------------------|---------|---------|
| High-confidence    | ≥ 80%   | Most findings are backed by deterministic or traced evidence. |
| Mixed-confidence   | 50–79%  | A significant share of findings rely on inference; targeted verification is recommended. |
| Low-confidence     | < 50%   | The majority of findings are pattern-inferred; a follow-up audit pass with scripted checks is advised. |
