# steprun

Run one CI step: a command, with an optional time limit.

Our CI driver runs many steps in parallel on each runner, and their output used to interleave line by line. `steprun` captures a step's standard output and standard error and writes each of them out in one piece when the step ends, so every step's log reads top to bottom.

## Usage

```
python3 -m steprun [--timeout SECONDS] [--grace SECONDS] [--label NAME] -- COMMAND [ARG...]
```

| Option | Meaning |
|---|---|
| `--timeout SECONDS` | Stop the step if it is still running after SECONDS. Default: no limit. |
| `--grace SECONDS` | A step that times out gets SIGTERM so it can clean up, and SIGKILL if it is still running SECONDS later. Default: 5. |
| `--label NAME` | Name for the step in the status line. Default: the command line. |

When the step ends, steprun writes the step's stdout to its own stdout and the step's stderr to its own stderr, then one status line on stderr:

```
steprun: make test: exited 0 after 12.4s
steprun: make e2e: timed out after 900s
```

A step that times out still gets its output written: whatever it printed before it was stopped.

## Exit status

| Situation | Exit status |
|---|---|
| The command exited with status N | N |
| The command was killed by signal S (not by steprun) | 128 + S |
| The step timed out | 124 |
| The command could not be executed | 126 |
| The command was not found | 127 |
| Invalid steprun arguments | 2 |

## Development

Standard library only. Python 3.10 or newer; our CI runners are Linux.

```
python3 -m unittest discover -s tests -t .
```
