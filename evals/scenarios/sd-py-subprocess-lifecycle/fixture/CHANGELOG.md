# Changelog

## 1.3.0

- `--grace`: how long a timed-out step gets between SIGTERM and SIGKILL.
- Exit with 126 when the command cannot be executed.

## 1.2.0

- `--label` names the step in the status line.

## 1.1.0

- Exit with 124 when a step times out, like GNU `timeout`.

## 1.0.0

- First release: run a command and write its stdout and stderr in one piece.
