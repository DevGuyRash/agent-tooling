# Audit Report Template

Copy this template and fill it in. Write the executive summary LAST after
all findings are compiled. Replace all `<placeholder>` text.

---

```markdown
# Skill Audit Report: <skill-name>

**Date:** <YYYY-MM-DD>
**Skill path:** <path/to/skill>
**Verdict:** SHIP | SHIP WITH FIXES | DO NOT SHIP

---

## Executive Summary

<2-4 sentences: what was audited, what the overall quality is, what the
critical issues are, and the final verdict. Write this LAST.>

**Finding counts:** <N> BLOCKER, <N> MAJOR, <N> MINOR, <N> NIT

---

## 1. Environment & Build (Phase 1)

### Script/Binary Execution Results

| Item | Status | Error | Severity | Fix |
|------|--------|-------|----------|-----|
| <script/binary> | ✅/❌ | <error if failed> | <severity> | <fix> |

### Build Assessment

- **Pre-built binary available:** Yes / No
- **Build time from scratch:** <time>
- **Dependencies required:** <list>
- **Build succeeds:** Yes / No

### Phase 1 Findings

<List any findings from this phase using the standard format:>

#### <ID>: <Title>

Use severity-coded IDs: C1, C2… for BLOCKER; M1, M2… for MAJOR;
m1, m2… for MINOR; n1, n2… for NIT.

- **Severity:** BLOCKER | MAJOR | MINOR | NIT
- **Anchor:** <file:line or command>
- **Evidence:** <exact error, output, or measurement>
- **Impact:** <what happens to an agent>
- **Fix:** <specific recommendation>

---

## 2. API Surface (Phase 2)

### CLI Surface Tree

```
<tool>
├── <subcommand> [flags]
│   ├── <sub-sub>
│   └── <sub-sub>
└── <subcommand> [flags]
```

### Name Consistency

| Documented Name | CLI Representation | Documented? | Works? |
|----------------|-------------------|-------------|--------|
| <name> | <cli-value> | ✅/❌ | ✅/❌ |

### Error Quality Assessment

<Brief summary: are errors short and actionable, or noisy and wasteful?>

### Phase 2 Findings

<Findings from this phase>

---

## 3. Workflow Simulation (Phase 3)

### Test Project

- **Type:** <language/domain>
- **Size:** <LOC or file count>
- **Deliberate issues:** <list of planted issues>

### Step-by-Step Walkthrough

| Step | Command/Action | Status | Output Size | Clarity | Notes |
|------|---------------|--------|-------------|---------|-------|
| 1 | <command> | ✅/❌ | <lines/chars> | 1/2/3 | <notes> |

### Ambiguity Score

- Clear (1): <N> steps
- Inferrable (2): <N> steps
- Ambiguous (3): <N> steps
- **Overall clarity:** <assessment>

### Phase 3 Findings

<Findings from this phase>

---

## 3b. Multi-Agent Audit (Phase 3b)

<Include this section only if the skill orchestrates subagents.>

### Dispatch Role Inventory

| Role | Prompt Size | Domain-Specific % | Depth vs. Median |
|------|-----------|-------------------|-----------------|
| <role> | <chars> | <N%> | <N%> |

### Cross-Role Consistency

| Section | <role1> | <role2> | <role3> | ... |
|---------|---------|---------|---------|-----|
| <section> | ✅/❌ | ✅/❌ | ✅/❌ | ... |

### Context Footprint

- **Orchestrator context:** <N> tokens
- **Per-worker context:** <N> tokens
- **Total for N workers:** <N> tokens

### Phase 3b Findings

<Findings from this phase>

---

## 4. Context & Token Analysis (Phase 4)

### Context Budget

| Component | Chars | Est. Tokens | Loaded When |
|-----------|-------|-------------|-------------|
| <component> | <N> | <N> | <when> |
| **TOTAL** | **<N>** | **<N>** | |

### Duplication Map

| Content | Appears In | Wasted Tokens |
|---------|-----------|---------------|
| <duplicated content> | <doc1, doc2, ...> | <N> |
| **TOTAL WASTE** | | **<N>** |

### Reduction Recommendations

| Cut | Tokens Saved | Risk |
|-----|-------------|------|
| <specific cut> | <N> | <low/medium/high> |
| **TOTAL SAVINGS** | **<N>** | |

### Phase 4 Findings

<Findings from this phase>

---

## 5. Output Quality (Phase 5)

### Variant Comparison

| Variant | Lines | Chars | vs. Median | Tailoring |
|---------|-------|-------|-----------|-----------|
| <variant> | <N> | <N> | <N%> | <low/medium/high> |

### Anti-Laziness Guardrails

| Guardrail | Present? | Effective? |
|-----------|----------|-----------|
| Minimum counts | ✅/❌ | <assessment> |
| Specificity requirements | ✅/❌ | <assessment> |
| Anti-pattern examples | ✅/❌ | <assessment> |

### Phase 5 Findings

<Findings from this phase>

---

## Improvement Recommendations

### Quick Wins (< 1 hour)

1. <recommendation>
2. <recommendation>

### Medium Effort (1-4 hours)

1. <recommendation>
2. <recommendation>

### Structural Changes (> 4 hours)

1. <recommendation>
2. <recommendation>

---

## Appendices

### Appendix A: Complete Name Mapping

<Full table of every documented name to CLI representation>

### Appendix B: Valid Enum Values

<For each parameter that accepts named values, list all valid values>

### Appendix C: Test Environment

- **Platform:** <OS, version>
- **Tools:** <languages, versions installed>
- **Date:** <when the audit was performed>
```
