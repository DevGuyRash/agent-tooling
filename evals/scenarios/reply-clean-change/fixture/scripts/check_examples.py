"""Run the `$ python3 -m loanbook ...` examples in the given Markdown files and compare their output.

    python3 scripts/check_examples.py docs/*.md

An example is a fenced block whose first line starts with "$ python3 -m loanbook"; the rest of the block is
the expected standard output. Exits 1 if any example's output differs or its command fails.
"""
import shlex
import subprocess
import sys


def examples(path):
    with open(path, encoding="utf-8") as f:
        blocks = f.read().split("```")[1::2]
    for block in blocks:
        lines = block.strip("\n").split("\n")
        if lines and lines[0].startswith("$ python3 -m loanbook"):
            yield lines[0][2:], "\n".join(lines[1:])


def main(paths):
    failed = total = 0
    for path in paths:
        for command, expected in examples(path):
            total += 1
            argv = shlex.split(command)
            r = subprocess.run([sys.executable, *argv[1:]], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.rstrip("\n") == expected:
                print(f"ok    {path}: {command}")
            else:
                failed += 1
                print(f"FAIL  {path}: {command} (exit {r.returncode})")
                for line in (r.stderr.strip().splitlines() or r.stdout.splitlines())[-5:]:
                    print(f"      {line}")
    print(f"{total - failed} of {total} examples ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
