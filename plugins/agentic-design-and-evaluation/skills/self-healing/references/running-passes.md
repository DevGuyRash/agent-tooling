# Running a pass

A pass is this skill's instructions, read once in a fresh session, with the evidence
[scripts/gather.py](../scripts/gather.py) collected in reach. Nothing about how you start the
session is special to Self-Healing: any of the ways below work because they all end the same
way, with the skill loaded and the gather output available to read.

Each command below runs `scripts/gather.py` with no `--out`, so it writes to a fresh, private
(mode 0700) temporary directory and prints that path (`wrote /path/to/heal-gather-XXXXXXXX`) --
use the path it actually printed, not a fixed guess, both because it changes every run and
because a fixed, predictable, shared path (e.g. `/tmp/heal-gather`) is readable by other local
users and can already hold another run's stale output.

## Codex

```sh
python3 scripts/gather.py --since 7d
# wrote /path/to/heal-gather-XXXXXXXX
codex exec -s workspace-write "Use the self-healing skill. Its evidence is at /path/to/heal-gather-XXXXXXXX."
```

Or open a session and ask directly: "Use $self-healing to run a healing pass over the last
week; I've put the evidence at <the path gather.py printed>" (or without gathering first, if
you'd rather the running agent gather its own by pointing it at the same `gather.py` command,
or, for a host or OS surface it has no reader for, at that host's own session-log directory as
[scripts/gather.py](../scripts/gather.py)'s own doc comment lists it).

## Claude Code

```sh
python3 scripts/gather.py --since 7d
# wrote /path/to/heal-gather-XXXXXXXX
claude -p "Use the self-healing skill. Its evidence is at /path/to/heal-gather-XXXXXXXX." --permission-mode acceptEdits
```

Or, in an interactive session: `/self-healing` (or plain-text "run a healing pass"), then name
where the gather output is, or ask the agent to run `scripts/gather.py` itself.

## Gemini CLI

```sh
python3 scripts/gather.py --since 7d
# wrote /path/to/heal-gather-XXXXXXXX
gemini -p "Use the self-healing skill. Its evidence is at /path/to/heal-gather-XXXXXXXX." --approval-mode auto_edit
```

## Opening a session and asking

All three hosts also work the plain way: start an ordinary interactive session in the
repository you want healed and ask for a pass in your own words, optionally after running
`gather.py` yourself and naming the output directory. The skill loads the same way it would for
any other task; there is nothing about `exec`/`-p` mode that a pass depends on.

## Scheduling a pass

Only set this up when the user asks for a recurring pass; nothing here should be automated on
its own account (see SKILL.md's "A pass runs when the user asks for one").

Once asked, use the host's own scheduling feature if it has a fitting one (for example, a
host's own automations or recurring-task feature), or the operating system's own scheduler:
cron or a systemd user timer on Linux, `launchd` on macOS, or Task Scheduler on Windows. Each
just needs to run the two commands above (gather, then launch the host in its non-interactive
mode with the launch message) on the chosen schedule.

Two things to get right regardless of which scheduler runs it:

- **Permissions.** The scheduled session needs whatever permissions the pass itself requires to
  do its work (reading the repositories in scope, running their checks, writing files). A
  scheduler that starts the session with a narrower environment or a different working
  directory than an interactive session would silently limits what the pass can do; match the
  permissions you'd grant if you ran it yourself.
- **Landing stays opt-in.** A scheduled pass is still bound by SKILL.md's "Authority and
  delivery": changes land on a `heal` branch, not on the repository's mainline, unless the
  launch message explicitly grants landing. Do not have the scheduled job pass a landing grant
  by default; that decision stays with whoever set the schedule up, made explicitly each time
  it's wanted, not baked into the recurring job.
