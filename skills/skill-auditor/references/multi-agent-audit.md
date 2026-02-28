# Multi-Agent Audit — Phase 3b

Read this document when the skill being audited orchestrates subagents. This
phase slots between Phase 3 (Workflow Simulation) and Phase 4 (Context
Analysis).

---

## Why multi-agent skills need special attention

When a skill dispatches work to subagents, every issue multiplies. A vague
dispatch prompt doesn't just confuse one agent — it confuses every worker that
receives it. A missing scope constraint doesn't just leak once — it leaks
across every parallel worker. The orchestrator-worker boundary is where the
most subtle bugs hide.

---

## Step 1: Inventory the dispatch system

Map every role the skill can dispatch. For each role, collect:

```
| Role | Dispatch mechanism | Prompt size | Domain-specific content |
|------|-------------------|-------------|----------------------|
| architecture-critic | mpcr protocol dispatch --role X | 2326 chars | 15% |
| ... | ... | ... | ... |
```

"Domain-specific content" is the percentage of the prompt that's unique to
this role vs. shared boilerplate. Measure it by diffing two prompts and
counting unique lines.

---

## Step 2: Prompt inspection

For each dispatch role, evaluate the prompt against these criteria:

### 2a: Self-containment

Can the worker do its job using ONLY the dispatch prompt? Check:

- Does the prompt contain or reference all necessary context?
  (file list, scope, acceptance criteria)
- Does it tell the worker where to find things it needs?
  (session dir, IDs, how to read files)
- Would the worker need to "figure out" anything that should be explicit?

An agent receiving a dispatch prompt should never need to read the skill's
SKILL.md or reference docs. The prompt IS their instructions.

**Common failure:** The prompt says "follow the reviewer protocol" but doesn't
include the protocol. The worker has no access to the skill's reference files.

### 2b: Scope containment

Does the prompt prevent the worker from exceeding its scope?

- Is there an explicit "forbidden commands" list?
- Are scope boundaries clear (file list, domain, responsibility)?
- Could a worker accidentally run orchestrator-level commands?
- Is the worker identity binding enforced (IDs, session, directory)?

**Common failure:** Worker prompts lack a "you SHALL NOT" section, and workers
drift into orchestrator behavior (running registration, spawning children).

### 2c: Output contract

Is the expected return format precisely specified?

- Is there an explicit output template in the prompt?
- Can the orchestrator mechanically validate the output?
  (check for required sections, parse structured data)
- What happens if the worker returns partial or malformed output?
  Is there a retry/fallback mechanism?

**Common failure:** Output format is described in prose ("return a summary of
findings") instead of as a template. Different workers return different formats,
making synthesis impossible.

---

## Step 3: Cross-role consistency

Compare all dispatch prompts against each other. This is where systematic
quality gaps surface.

### 3a: Depth consistency

Measure the size (lines, chars) of every dispatch prompt. Calculate the median.
Flag any role where:
- Size < 60% of median → likely **too shallow**
- Size > 200% of median → possibly **over-specified** or **duplicating context**

Plot or table the comparison:
```
| Role | Lines | Chars | vs. Median |
|------|-------|-------|-----------|
| architecture-critic | 66 | 2326 | 100% (median) |
| observability-oncall | 33 | 1658 | 71% |
| docs-consumer | 32 | 1514 | 65% ⚠️ |
```

### 3b: Structural consistency

Define the "expected sections" from the most complete prompt. Then check which
sections each role has:

```
| Section | arch-critic | security | observability | docs |
|---------|------------|----------|--------------|------|
| Worker identity | ✅ | ✅ | ✅ | ✅ |
| Assigned scope | ✅ | ✅ | ✅ | ✅ |
| Domain focus | ✅ | ✅ | ✅ | ✅ |
| Context budget | ✅ | ✅ | ❌ | ❌ |
| Task steps | ✅ | ✅ | ✅ | ✅ |
| Output template | ✅ | ✅ | ❌ | ❌ |
```

Missing sections in some roles but not others = inconsistency finding.

### 3c: Domain tailoring

For each prompt, identify content that's specific to its domain vs. shared
boilerplate. A well-tailored prompt should have:
- Domain-specific "defend that..." statement
- Domain-specific seed challenges (not generic "look for issues")
- Domain-specific disproof techniques (how to break things in this domain)
- Domain-specific anti-laziness guidance

If a prompt is >80% boilerplate, the worker won't produce domain-specific
insights. Flag as MAJOR.

### 3d: Shared boilerplate analysis

Identify text that appears verbatim (or near-verbatim) across all prompts.
This is context that's being paid for N times (once per worker) instead of
once. Calculate the waste:

```
Shared boilerplate per prompt: ~800 chars
Number of roles: 20
Total redundancy: 20 × 800 = 16,000 chars (~4,000 tokens)
```

Can the shared content be moved into a "worker preamble" that's separate from
the domain-specific content?

---

## Step 4: Orchestrator-worker interface

Test the handoff points between orchestrator and workers.

### 4a: Dispatch → Worker

When the orchestrator creates a dispatch prompt, what does it need to fill in?
Look for placeholders like `[ORCHESTRATOR FILLS IN]`. For each:
- Is it clear what the orchestrator should provide?
- Is there a risk the orchestrator skips it or provides wrong data?
- What happens to the worker if the placeholder isn't filled?

### 4b: Worker → Orchestrator

When the worker returns results, how does the orchestrator consume them?
- Does the orchestrator parse structured output or read free-form text?
- If structured, is the format enforced (JSON schema, required fields)?
- If free-form, how does the orchestrator extract findings?

### 4c: Error propagation

What happens when a worker fails?
- Does the orchestrator detect the failure?
- Is there a retry mechanism?
- Is there a graceful degradation path?
- What if the worker returns results for the wrong scope?

---

## Step 5: Context amplification analysis

Calculate the total context footprint across all agents:

```
Orchestrator context:
  SKILL.md:                    4,500 tokens
  Protocol outputs:            3,000 tokens
  Subagent results (pending):  N × ~500 tokens
  Total orchestrator:          ~10,000 tokens

Per-worker context:
  Dispatch prompt:             ~580 tokens
  Code context (explorer):     ~1,000 tokens
  Total per-worker:            ~1,580 tokens

Cross-agent total for 20-worker review:
  Orchestrator:                10,000 tokens
  Workers (20 × 1,580):       31,600 tokens
  GRAND TOTAL:                 41,600 tokens
```

This is the skill's "context footprint" — the total tokens consumed across
all agents for one invocation. Compare to the actual work done (lines of code
reviewed, findings produced) to assess efficiency.

---

## What to record

1. Dispatch role inventory table
2. Per-role prompt evaluation (self-containment, scope, output contract)
3. Cross-role consistency tables (depth, structure, tailoring)
4. Shared boilerplate analysis with waste calculation
5. Interface evaluation (dispatch → worker → orchestrator)
6. Context footprint calculation

---

## Common findings in multi-agent skills

These patterns come up frequently. Check for them explicitly:

| Pattern | Severity | What to look for |
|---------|----------|-----------------|
| Undocumented role slugs | BLOCKER | Domain names don't match dispatch role names |
| Shallow minority roles | MAJOR | Some roles have <60% median prompt depth |
| No output template | MAJOR | Workers return free-form text, synthesis is ad-hoc |
| No scope containment | MAJOR | Workers can run orchestrator commands |
| Excessive boilerplate | MINOR | >60% of each prompt is shared text |
| No retry mechanism | MINOR | Failed workers are silently dropped |
| No concurrency enforcement | MINOR | Cap is documented but not enforced by tooling |
