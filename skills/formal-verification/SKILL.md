---
name: formal-verification
description: Verify one property of a repository's code in every case within a stated scope (every interleaving of a model, every input up to a bound, or every input) with a model checker, proof assistant, code-level verifier, or generated-input testing, in any language. Use for "model-check this", "prove this invariant", races, retries, idempotency, state machines, parsers, overflow, unsafe or FFI code, or when tests cannot reach the cases that break.
---

# Formal Verification

A test checks the cases someone thought to write. This skill checks every case in a stated scope, so its result is only as good as the scope and the model's fidelity to the code. The user must be able to trust the result and act on it without reading the verification language.

## 1. Use what the repo already has

Look for a repo-local formal verification skill and for existing specs or proofs (`*.tla` with `*.cfg`, `#[kani::proof]` harnesses, `*.dfy`, Lean, Rocq, Isabelle, Alloy, CBMC harnesses, property tests). When a repo-local skill covers the code you are changing, follow it; where it differs from this skill, it wins. When the covered code changed after the skill's recorded sync commit, bring the verification back in line first (pstack's `maintain-formal-verification-skill` covers this).

## 2. Choose the target

Start from the area or bug the user named. Otherwise pick the strongest target in the repo, not the easiest to verify: a promise the code makes where a break harms users and tests rarely reach the case that breaks it. Before modeling, write the property and the harm in one plain sentence each.

## 3. Let the question choose the tool

- **Whether events can happen in a bad order** (races, retries, async or distributed protocols): a model checker over a small model of the design. TLA+ with TLC is the default in any language.
- **Whether the code behaves for every input** (memory safety, overflow, a data-structure invariant): a verifier that runs on the code itself, such as Kani for Rust or CBMC for C.
- **Whether a property holds at every size**, where a bound is not enough: a proof.
- **No verifier runs on this language:** say so, and test the real code with generated inputs (a property-based testing library), not a hand model of the function. Report that as bounded testing, not proof.

Prefer a tool the repo's developers can install and run, pin its version, and tell the user why you chose it.

## 4. Make the result trustworthy

- **True to the code.** Every part of the model points to a file and function a reviewer can open, what the model treats as one atomic step is one atomic step in the code, and names come from the repo.
- **Able to fail.** Show each property failing on a broken variant of the real code it guards, such as a removed check or a reordered step, then restore the code and confirm the check returns to where it started.
- **Findings stay findings.** When the current code breaks the property, report the counterexample as a short sequence of steps in the code's words. The property and model keep their meaning; product code changes only when the user asks.
- **Honest scope.** State the bounds, the assumptions, and what is left out. A pass covers the model or the bound, not the whole system.
- **Cheap to rerun.** One command, a pinned tool version, and a run short enough to repeat on every change to the covered code.
- **Contained.** Stop only the checker runs you started, by their PID.

Verification files belong to the repo they verify, placed where it keeps its tooling and added under its contribution rules. When the user or the repo's rules keep them out of the tree, put them in `${XDG_STATE_HOME:-$HOME/.local/state}/formal-verification/<repo>/` and say so.

## 5. Report, then offer to persist

Tell the user the property and its harm, the tool and why, the bounds and assumptions, what the check found in plain words, how to rerun it, and what it does not cover. When the covered code will keep changing, offer once to persist the check as a repo-local skill with pstack's `create-formal-verification-skill`, which records the covered files and a sync commit so later changes get rechecked.
