# Clipboard and Latency Guidance

## Typical latency sources

- blocking clipboard subprocesses
- backend mismatch (Wayland vs X11 assumptions)
- mixing payload output with status-only messages

## Recommended behavior model

- `print_only`
  - fastest option when script output is the final replacement text.

- `dual_output`
  - print payload immediately
  - perform clipboard write as best-effort side effect

- `clipboard_only`
  - if no payload text is intended, keep replacement deterministic
  - avoid user-facing status text replacing expected content

## Session-aware backend hints

- Wayland sessions: prefer `wl-copy` when `WAYLAND_DISPLAY` exists
- X11 sessions: prefer `xclip` or `xsel` when `DISPLAY` exists
- Linux clipboard helpers: prefer `wl-copy`, `xclip`, or `xsel` based on the active session

## Failure policy

- do not block user-visible output on clipboard failures
- route diagnostics to logs/stderr, not replacement payload
