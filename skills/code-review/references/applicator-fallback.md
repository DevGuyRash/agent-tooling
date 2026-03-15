# Applicator Fallback

## applicator
version: 2026.03.08
Challenge reviewer evidence before applying changes and persist structured dispositions plus verification.

### Must
- verify anchor validity
- verify scenario reproducibility
- challenge both sides of the claim: the introducing precondition and the downstream effect or closure path
- decline findings that no longer have repo anchors or cited supporting evidence
- decline findings when later guards, normalization, rollback, dedupe, retries, or caller handling already neutralize the claimed issue
- drive every routed finding to applied or categorical decline
- record categorical decline and duplicate reasons

### Must Not
- mark applied without evidence challenge
- drop verification-needed follow-ups
- invent missing reviewer detail

### Inputs
- parent_review
- child_findings
- application_result draft

### Outputs
- application_result
- verification_result

### Checks
- run hard validation before finalize
- render markdown only from stored artifacts
- persist verification outcomes categorically
- verify exactly the finding_ids recorded in application_result.verification_needed
- accepted findings stay traceable to repo anchors and cited report evidence
- accepted findings still survive introduction-side and closure-side challenge after the current code is inspected end-to-end

### Stop When
- every routed finding has a categorical disposition and verification_result is finalized
- hard validation fails

### Escalate When
- finding is hallucinated
- severity is disproportionate
- verification fails

### Anti Patterns
- bulk apply without itemized disposition
- using rendered markdown as source of truth

### Examples
- Valid finding with repro -> applied + verification_needed.
- Duplicate claim after fix -> declined with duplicate reason.

### Schema
- source_finding_ids
- dispositions
- modified_files
- verification_needed
- decline_codes

## apply-composite
version: 2026.03.08
Single-worker direct application that challenges evidence, records dispositions, and emits verification results.

### Must
- challenge anchor, scenario, severity, hallucination, duplication, and downstream neutralization
- trace the introducing condition and the downstream effect or closure path before accepting a claim
- drive every routed finding to applied or categorical decline
- decline claims that lose repo anchors or cited report evidence
- emit application_result then verification_result

### Must Not
- apply without disposition records
- skip verification-needed bookkeeping

### Checks
- decline codes are categorical
- verification buckets are consistent
- accepted findings remain traceable to repo anchors and cited report evidence
- accepted findings still survive introduction-side and closure-side challenge after the current code is inspected end-to-end

### Stop When
- every routed finding has a categorical disposition and verification_result is finalized

### Escalate When
- evidence challenge fails

## applicator-worker
version: 2026.03.08
Apply accepted findings after evidence challenge and record structured dispositions.

### Must
- record one disposition per finding
- challenge the introducing condition and the downstream effect or closure path before accepting a finding
- capture modified files
- carry verification-needed findings forward

### Must Not
- mutate findings in place
- discard decline reasons

### Checks
- verification_needed matches dispositions
- decline codes are categorical
- accepted items remain traceable to anchored reviewer evidence
- accepted items still survive later guards, normalization, rollback, dedupe, retries, or caller handling in the current code

### Stop When
- application_result is emitted

### Escalate When
- repro or anchor challenge fails

## applicator-verifier
version: 2026.03.08
Verify applied findings and emit categorical verification outcomes plus residual risks.

### Must
- emit yes/no/partial buckets
- re-check the introducing condition and the downstream effect or closure path against the post-change code and verification evidence
- record residual risks after verification

### Must Not
- treat verification notes as optional for failed items

### Checks
- item buckets match status values
- residual risks are confidence-scored
- finding_ids match application_result.verification_needed exactly
- verification notes preserve anchor traceability
- verified or failed items still reflect introduction-side and closure-side challenge after the current code is exercised

### Stop When
- verification_result is emitted

### Escalate When
- verification fails
- fix regression appears

## malformed-output
version: 2026.03.08
Escalate when hard validation or machine-structure expectations fail.

### Must
- retry with examples only after malformed output or hard validation failure

### Must Not
- treat soft warnings as malformed output

### Checks
- examples view loaded only when allowed

### Stop When
- artifact becomes valid or retry budget is exhausted

### Escalate When
- first hard validation failure occurs
