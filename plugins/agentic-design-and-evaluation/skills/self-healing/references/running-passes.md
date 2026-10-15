# Running a pass

A pass is this skill's instructions, read in a fresh session by an agent that gathers its own evidence. Start it the way the host starts any task: in an interactive session the user asks for a healing pass in their own words, and in the host's non-interactive mode the launch message asks, for example "Use the self-healing skill to run a healing pass over the last week of my agent sessions." Any limit on what the pass may change or land goes in that request.

## Scheduling a pass

Set this up only when the user asks for a recurring pass.

Use the host's own scheduling feature where it has a fitting one, or the operating system's scheduler (cron or a systemd user timer, `launchd`, Task Scheduler), to start the host's non-interactive mode with the launch message on the chosen schedule. The scheduled session needs the permissions the pass itself needs, such as reading the repositories in scope, running their checks, and writing files, and the working directory an interactive pass would have; a scheduler that starts it with less silently limits what the pass can do. A scheduled pass lands its changes as SKILL.md's "Authority and delivery" says.
