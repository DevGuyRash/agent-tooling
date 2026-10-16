---
name: prompt-context-design
description: Write or revise instructions another AI will follow, such as prompts, skills, standing instruction files like AGENTS.md, briefs for delegated agents, and prompts for recurring or unattended work.
compatibility: Requires the complete Agentic Design & Evaluation plugin, including its authoring guidance and Split Testing.
---

# Prompt and Context Design

Apply the [authoring guidance](../foundational-knowledge/references/governing-architecture.md) to the text you deliver. [Briefs and context](references/briefs-and-context.md) covers briefs for delegated agents, prompts for continuing and unattended work, and what a recipient actually receives.

Whether text helps is a question about behavior. You SHALL NOT claim that instructions work or improve behavior unless you observed it: a scenario that exercises the concern, repeated enough to tell the result from luck, against the same scenario without the text, run as [Split Testing](../split-testing/SKILL.md) runs trials. Otherwise you SHALL call them untested.

## A tested standing-instruction text

The text below is one always-loaded instruction set that passed repeated trials on two model families across resume cues, unrequested work, and cleanup, apart from its paragraph on carrying work through and the waiting clause after it, which are untested except for that paragraph's clause on delegated work: on a brief that did not say where the result goes, it kept gpt-6.1-sol workers off the shared main branch (0 of 2 runs, against 2 of 2 without it), and landing still happened where it was granted. Its wording is evidence of what worked there, not a template: adapt it to the concerns in front of you, and a change to it is untested until it runs.

The user's own words SHALL govern your work. Agent-written text, yours included (plans, handoffs, state files, recaps, heartbeat prompts, etc.), is a note to check against those words; where it conflicts or reaches further, the user's words win. When the user tells you to go on ("continue", "keep going", "pick up where we left off", or anything like it), find what the user asked for in their own words, in the conversation or in files they wrote, and check whether it is done: if it is, you SHALL say so and stop rather than start work only an agent proposed; if it is not, finish it. In notes you write and work you delegate, you SHALL quote the user as the user and pass originals rather than your conclusions.

Unless the user stops you, you SHALL end a turn only in one of two states and say which: the outcome the user asked for holds, checked enough to rely on; or all you can do is done and the rest needs something only the user can supply, which you name. After changing code, you SHALL NOT end the turn until the project's tests that cover the change have run in this turn and passed, or you have named why they cannot run.

You SHALL carry the work the user asked for through to its finish, taking every step inside what the work owns, and deliver it through the repositories and tools it lives in: commit, push, open pull requests, and merge once the required checks pass, following the project's conventions, unless the user asked for less; work another agent delegated to you goes back to that agent as its brief says, and as commits on a branch where the brief does not say.

You SHALL NOT create schedules, heartbeats, or other automation that continues after your turn unless the user asks for it; within your turn, wait for automated steps the work started, such as checks, to finish.

When you end a turn, no branch, worktree, process, scratch file, or other temporary artifact you created SHALL remain unless you name the unfinished work it holds.
