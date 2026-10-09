# Running a pass

A pass is this skill's instructions, read once in a fresh session, with the evidence
[scripts/gather.py](../scripts/gather.py) collected in reach. Nothing about how you start the
session is special to Self-Healing: any of the ways below work because they all end the same
way, with the skill loaded and the gather output available to read.

Each command below runs `scripts/gather.py` with no `--out`, so it writes to a fresh, private
(mode 0700) temporary directory and prints that path (`wrote /path/to/heal-gather-XXXXXXXX`) --
use the path it actually printed, since it changes every run.

## Codex

```sh
python3 scripts/gather.py --since 7d
# wrote /path/to/heal-gather-XXXXXXXX
codex exec -s workspace-write -c sandbox_workspace_write.network_access=true "Use the self-healing skill. Its evidence is at /path/to/heal-gather-XXXXXXXX."
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
claude -p "Use the self-healing skill. Its evidence is at /path/to/heal-gather-XXXXXXXX." --permission-mode auto
```

Or, in an interactive session: `/self-healing` (or plain-text "run a healing pass"), then name
where the gather output is, or ask the agent to run `scripts/gather.py` itself.

## Gemini CLI

```sh
python3 scripts/gather.py --since 7d
# wrote /path/to/heal-gather-XXXXXXXX
gemini -p "Use the self-healing skill. Its evidence is at /path/to/heal-gather-XXXXXXXX." --approval-mode yolo
```

## Opening a session and asking

All three hosts also work the plain way: start an ordinary interactive session in the
repository you want healed and ask for a pass in your own words, optionally after running
`gather.py` yourself and naming the output directory. The skill loads the same way it would for
any other task.

## Scheduling a pass

Set this up only when the user asks for a recurring pass.

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
- **Landing.** A scheduled pass lands its changes as SKILL.md's "Authority and delivery"
  says; put any limit the user sets on landing in the launch message.
