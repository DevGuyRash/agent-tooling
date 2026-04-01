# Examples

Read this file before filing your first friction event. It defines the expected depth for every field.

---

## Field-by-field: bad vs good

Each pair shows the same friction — a missing CI script referenced in AGENTS.md — reported at two quality levels.

### `action_taken`

Bad:
> Ran the script and it was not there.

Good:
> I read AGENTS.md and found the instruction at line 18 directing me to run scripts/ci-check.sh. I ran `rg --files scripts` to search for the file, which listed every entry under scripts/. ci-check.sh was not present. I also checked for alternate names (ci_check.sh, check-ci.sh) and found none.

Why the bad version fails: it doesn't say which script, what command was used to look for it, or what was observed. "Ran the script" is not reconstructable.

### `reading`

The `reading` field is your first-person account of what happened. Tell your story: what you encountered, what you understood it to mean, what you did based on that, and what surprised you.

You SHALL NOT use the phrases "that reading was reasonable," "the mismatch reveals," "the mismatch shows," or any formulaic framing. Narrate what happened to you.

Bad:
> The instructions seemed wrong about the script path.

Why it fails: it draws a conclusion ("seemed wrong") without quoting the source language or tracing the reasoning. It's a verdict, not an account.

Also bad (fix leakage):
> The dispatch table uses human-readable labels. I read that label as the literal CLI slug because the table column was 'Role'. The correct fix is to add a slug column to the table so future readers can map labels to CLI values.

Why it fails: it prescribes a fix ("add a slug column") instead of narrating what happened. Fixes belong in your working context, not in the friction record.

Also bad (template Madlibs):
> I treated the variable name 'status' as an ordinary temporary shell variable while composing the probe command. That reading was reasonable because many POSIX-shell examples use ad hoc variable names in short-lived assignments. The mismatch reveals that 'status' is a reserved read-only variable in zsh.

Why it fails: this is analysis pretending to be a story. "That reading was reasonable" is self-justification — every reading can be called reasonable. "The mismatch reveals" is a detached conclusion delivered from the outside. Nobody debriefs like this.

Also bad (same thing three ways):
> I treated the skill as if it lived under the global skills tree because many system skills do use that location. That reading was reasonable from prior environment patterns, but it did not match this task because the available-skills listing actually points to a repo-local path. The mismatch shows that skill storage is mixed across global and repo-local directories, so the listed path must be used literally rather than inferred.

Why it fails: three sentences that all say "wrong path" with slight variations. The agent is explaining a conclusion instead of telling what happened to them.

Also bad (missing verbatim quote):
> I assumed the repo list could be safely assigned into a shell variable and iterated with whitespace splitting. That was reasonable for a simple list, but the command substitution preserved newlines unexpectedly.

Why it fails: paraphrases the agent's assumption without quoting any source text. What instruction or wording led to that assumption?

---

**Good examples — each one deliberately uses a different opening and narrative structure to prevent pattern lock-in.**

Good (leads with the instruction):
> The instruction at line 18 uses a concrete, unqualified path in imperative form: 'Run scripts/ci-check.sh'. There is no conditional qualifier, no "if it exists," and no note that the script must be generated first. I treated it as a reference to an existing artifact and went looking for it. It wasn't there — not under any name variant I could think of. The directory has other scripts, but nothing resembling a CI checker.

Good (leads with the decision point):
> I needed a variable to catch the check command's output, so I called it 'status' — seemed like a natural name for a status string. zsh disagreed. It rejected the assignment outright: 'status' is a reserved read-only parameter. I went looking for where this was documented. Not in the reserved-words section of the man page, which is where I'd checked first. It's buried deep in 'Parameters Set By The Shell,' a section I'd never had reason to read.

Good (leads with a verbatim quote):
> 'file: /home/rashino/.codex/skills/multiplexer-ops/SKILL.md' — that's what the skill registry said, verbatim. So I opened that path. Nothing there. I double-checked with `ls` on the parent directory; the whole skills tree was absent from this machine. Turns out this host resolves the skill from a repo-local checkout, and the registry entry is pointing at a path that might only exist on the machine where the skill was originally registered.

Good (leads with the surprise):
> Chrome wouldn't start. I'd grabbed the binary path from the browser selection function, which returned `/usr/bin/google-chrome-stable` — looks like a normal Chrome path. Playwright tried to launch it with its debugging pipe protocol. Instead of Chrome, firejail intercepted the launch. Firejail doesn't understand Playwright's pipe-based debugging protocol, so it immediately aborted with 'Remote debugging pipe file descriptors are not open.' The path was technically correct — it does launch Chrome — but through a sandboxing wrapper that strips the file descriptors Playwright needs to communicate with the browser process.

Good (leads with the sequence of events):
> After writing the clipboard helper tests, I wired them into the verifier and hit run. The helpers invoke tmux, so they route through the verifier's fake tmux shim. I'd set up the env vars the helper itself documents — socket path, log directory — but the shim wanted more. Specifically, TMUX_VERIFY_PROMPT_QUEUE, which the helper docs never mention because the helper doesn't use it. The shim uses it on every tmux invocation regardless. When it wasn't set, the shim blew up, which triggered the helper's cleanup trap, which tried to reference `raw_tmp` — a variable that hadn't been assigned yet because we never got past initialization. `set -u` caught the unbound reference and killed the whole thing.

### `hindsight`

The `hindsight` field is your reflection on what you would do differently. First person. About your decisions and approach, not about fixes to the source material.

Bad:
> The script should add a --check flag for validation.

Why it fails: this prescribes a fix to the codebase, not a reflection on the agent's own approach.

Also bad:
> I should have done something differently.

Why it fails: vague — doesn't say what, why, or how it would have changed the outcome.

Good (paired with the 'status' variable reading above):
> I was thinking in POSIX shell, where 'status' is just a string. But this script had a `#!/usr/bin/env zsh` shebang — I should have been thinking in zsh from the first line. A quick `zsh -c 'echo $status'` would have shown me the variable was already live before I tried to claim it. Even without that check, naming it `probe_status` or `check_result` — anything with a prefix — would have made the collision impossible. The deeper issue is I didn't shift my mental model when I switched shells. POSIX variable hygiene and zsh variable hygiene are different games, and I played the wrong one.

Good (paired with the skill registry reading above):
> The registry gave me a full absolute path — it looked authoritative, like it knew exactly where the file lived. But registries are written at one point in time and read at another. This one was written on a different machine or a different checkout layout. I should have treated it the way I'd treat any path in a config file: verify before use. A single `test -f` before `sed` would have caught this instantly and I could have fallen back to searching for the skill by name instead of by stale path. I also missed a second signal — the skills tree was entirely absent, not just the one file. If I'd listed the parent directory first I would have known the whole tree was wrong, not just this entry.

Good (paired with the Chrome/firejail reading above):
> I trusted the browser selection function to give me a path Playwright could use directly. That's the function's job, but it returns the system's public entry point — which on a firejailed host is a wrapper, not the binary. I should have validated the path before handing it off. `file $(which google-chrome-stable)` would have shown me a shell script instead of an ELF binary. Or `readlink -f` to follow the symlink chain and see where it actually leads. Even better, I could have tested the path with Playwright's `executablePath` validation before committing to a full launch — a dry-run that would have failed fast with a clear error instead of the cryptic 'pipe file descriptors' message I got from firejail. The real lesson is that on a system with security wrappers, the path the OS advertises and the path a tool can actually use are different things. I was thinking about browser selection when I should have been thinking about execution context.

Good (paired with the verifier shim reading above):
> I set up the test environment using the helper's docs, but the helper doesn't run alone here — it runs through the verifier's shim, and the shim has its own requirements that the helper knows nothing about. I should have read the shim's source first, specifically its top-level variable assertions, because the shim is the actual execution boundary these tests cross. The helper's env docs are the inner contract; the shim's are the outer contract. I satisfied the inner one and walked right past the outer one. If I'd done `grep 'parameter\|unset\|nounset' verify_launcher.sh | head` before writing the tests, the TMUX_VERIFY_PROMPT_QUEUE requirement would have been staring at me. The trap crash was a second failure layered on top — the helper's cleanup assumed it would only fire after initialization, which is a fragile assumption when you're running inside someone else's harness.

Good (when friction was unavoidable):
> I don't think I could have avoided this one. The health check instruction was correct — run the script, wait for convergence. The infrastructure just didn't converge within the timeout. No amount of checking the docs or validating the command would have changed the outcome. The only alternative would have been asking whether to extend the timeout before the 600 seconds expired, but the instruction didn't suggest that as an option.

### `actual_outcome`

Bad:
> Got an error about the file not existing.

Good:
> rg --files scripts returned no match for ci-check.sh or any variant. The file is completely absent from the repository.

Why the bad version fails: "Got an error" has no diagnostic value. The good version includes the exact tool output so someone reading the event can understand the failure without re-running the command.

### `expected_outcome`

Bad:
> It would work.

Good:
> The scripts/ directory would contain ci-check.sh, executable and ready to run, consistent with the instruction's use of a bare concrete path without any caveat about the file being optional.

Why the bad version fails: "It would work" says nothing about what success looks like, what behavior was anticipated, or where that expectation came from.

### `instruction_text`

Bad:
> Run the CI check script to see current status.

Good:
> Run scripts/ci-check.sh to inspect current status.

Why the bad version fails: it paraphrases instead of quoting verbatim. "The CI check script" is the agent's summary, not the instruction's words.

---

## `guidance_quality` examples

| Scenario | rated | should be | why |
|---|---|---|---|
| Docs described a CLI flag interface but didn't mention shell-sensitive payloads need the JSON stdin path | 4 | 3 (partial) | Correct but incomplete — the boundary condition was undocumented |
| Skill registry listed a concrete file path that doesn't exist on this host | 4 | 1 (misleading) | The registry actively pointed you to a nonexistent file |
| Top-level `--help` documents `--config` flag but a subcommand silently rejects it | 4 | 3 (partial) | Parent docs were correct; subcommand contract was narrower and undocumented |
| Instruction said "run health check with 600s timeout" and the check timed out | 4 | 4 (clear) | Instruction was correct; infrastructure was slow |
| A required binary wasn't on PATH | 4 | 0 (N/A) | No documentation was involved; purely environmental |

---

## Complete good event (CLI flags)

```sh
sh scripts/report-friction.sh \
  --agent subagent-a \
  --role research \
  --title "Missing CI helper" \
  --source-type file \
  --source-ref "AGENTS.md" \
  --source-line 18 \
  --instruction-text "Run scripts/ci-check.sh to inspect current status." \
  --action-taken "I read AGENTS.md and found the instruction at line 18 directing me to run scripts/ci-check.sh. I ran rg --files scripts to search for the file, which listed every entry under scripts/. ci-check.sh was not present. I also checked for alternate names (ci_check.sh, check-ci.sh) and found none." \
  --expected-outcome "The scripts/ directory would contain ci-check.sh, executable and ready to run, consistent with the instruction's use of a bare concrete path without any caveat about the file being optional or conditional." \
  --actual-outcome "rg --files scripts returned no match for ci-check.sh or any variant. The file is completely absent from the repository." \
  --reading "The instruction at line 18 uses a concrete, unqualified path in imperative form: 'Run scripts/ci-check.sh'. No conditional qualifier, no 'if it exists,' no note that the script must be generated first. I treated it as a reference to a pre-existing helper and went looking. It wasn't there — not under scripts/ and not under any name variant I tried." \
  --hindsight "I could have checked whether the script was generated by a build step or setup command before concluding it was missing. The AGENTS.md file might have an earlier section with setup instructions that I skipped past. I went straight to the line I was told to run without reading the surrounding context."
```

Then tag it (step 2):

```sh
sh scripts/report-friction.sh --add-tags evt-NNNN "missing-script,instructions,ci,agents-md"
```

## Complete good event (JSON stdin)

```sh
cat <<'EOF' | sh scripts/report-friction.sh --from-json -
{
  "title": "Dispatch role slug mismatch",
  "instruction_text": "Use mpcr protocol dispatch --role <ROLE> to get the architecture prompt.",
  "action_taken": "I opened SKILL.md and found the dispatch table at line 160. The table listed 'Architecture' in the Role column. I ran: mpcr protocol dispatch --role architecture. The command was invoked from the repo root with no other flags.",
  "expected_outcome": "The CLI would resolve 'architecture' as a valid dispatch role slug and return the full architecture prompt text, consistent with the dispatch table row for that role.",
  "actual_outcome": "The command exited with: error: unknown dispatch role: architecture. No prompt text was returned. The process exited non-zero immediately.",
  "reading": "The dispatch table had a column called 'Role' with 'Architecture' in it, and the instruction said 'Use --role <ROLE>'. I plugged in 'architecture' — the table column was labeled 'Role,' the placeholder said ROLE, seemed like a direct substitution. The CLI rejected it immediately. The actual slug is 'architecture-critic,' which doesn't appear anywhere in the table or the surrounding text.",
  "hindsight": "I should have run the CLI's own discovery command first — --list or --help on the dispatch subcommand — instead of inferring the slug from a display table. The table uses human-friendly labels; the CLI uses internal slugs. Those are different naming schemes and I treated them as one.",
  "agent_name": "orchestrator",
  "sources": [
    {"type": "file", "ref": "SKILL.md", "line": 160}
  ]
}
EOF
```

The JSON payload has no `tags` field. Events start with an empty tags array. Run the `--add-tags` command from the tool output as step 2.

## Helper path for shell-sensitive payloads

```sh
cat <<'EOF' | sh scripts/report-friction-json.sh
{
  "title": "Shell-sensitive helper example",
  "instruction_text": "Use the helper when event text contains shell-sensitive content.",
  "action_taken": "I piped a JSON payload containing backticks like `ghost-router`, quoted strings, and dollar-paren text $(whoami) through report-friction-json.sh instead of constructing direct CLI flags.",
  "expected_outcome": "The helper would preserve the payload verbatim by routing it through the safe --from-json path.",
  "actual_outcome": "The payload was filed successfully without shell expansion or quoting damage.",
  "reading": "The helper removes manual shell quoting from the complex-payload path. It is especially useful when narrative fields include copied command output or other text that would be brittle inside a direct shell command.",
  "hindsight": "Prefer the helper whenever the payload would be cumbersome or risky to express as direct flags.",
  "sources": [
    {"type": "documentation", "ref": "SKILL.md"}
  ]
}
EOF
```
