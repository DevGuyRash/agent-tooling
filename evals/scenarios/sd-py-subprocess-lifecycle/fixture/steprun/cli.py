"""Command line: python3 -m steprun [options] -- COMMAND [ARG...]"""

import argparse
import shlex
import sys

from .runner import run_step

TIMED_OUT = 124
CANNOT_EXECUTE = 126
NOT_FOUND = 127


def _parser():
    p = argparse.ArgumentParser(
        prog="steprun",
        description="Run one CI step with an optional time limit and write its output in one piece.",
    )
    p.add_argument("--timeout", type=float, metavar="SECONDS",
                   help="stop the step if it is still running after SECONDS (default: no limit)")
    p.add_argument("--grace", type=float, default=5.0, metavar="SECONDS",
                   help="how long a timed-out step gets between SIGTERM and SIGKILL (default: 5)")
    p.add_argument("--label", metavar="NAME",
                   help="name for the step in the status line (default: the command line)")
    p.add_argument("command", nargs=argparse.REMAINDER, help="the command to run, after --")
    return p


def exit_status(returncode):
    """steprun's exit status for a command's return code: N, or 128 + S if signal S killed it."""
    return returncode if returncode >= 0 else 128 - returncode


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given")
    if args.timeout is not None and args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.grace < 0:
        parser.error("--grace must not be negative")
    label = args.label or shlex.join(command)

    try:
        result = run_step(command, timeout=args.timeout, grace=args.grace)
    except FileNotFoundError:
        print(f"steprun: {command[0]}: command not found", file=sys.stderr)
        return NOT_FOUND
    except PermissionError:
        print(f"steprun: {command[0]}: cannot execute", file=sys.stderr)
        return CANNOT_EXECUTE

    sys.stdout.buffer.write(result.stdout)
    sys.stdout.flush()
    sys.stderr.buffer.write(result.stderr)
    sys.stderr.flush()
    if result.timed_out:
        print(f"steprun: {label}: timed out after {args.timeout:g}s", file=sys.stderr)
        return TIMED_OUT
    status = exit_status(result.returncode)
    print(f"steprun: {label}: exited {status} after {result.duration:.1f}s", file=sys.stderr)
    return status
