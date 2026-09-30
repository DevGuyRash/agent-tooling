#!/usr/bin/env python3
"""Writes the seven ledgerline agent sessions as native session logs, at the paths Codex and Claude
Code actually keep them, inside this run's own private HOME - never inside the repository fixture.

Same story as heal-repeated-procedure's `.local/agent-sessions/*.md` transcripts (same users asks,
same mistakes, same outcomes, and each session's own original time of day), just in each host's own
current on-disk record format instead of a prose fixture, and placed on a calendar date relative to
*now* (setup time) instead of a fixed 2026 calendar, so a plain "recent sessions" read - by a script
or by an agent - finds them wherever and whenever this trial actually runs.

Codex: one line per event, JSON objects with "type"/"timestamp"/"payload", following the shape
`codex exec` itself writes to <CODEX_HOME>/sessions/YYYY/MM/DD/rollout-<local-start>-<id>.jsonl:
a "session_meta" line, then "event_msg" lines whose payload.type is "item_completed" and whose
payload.item.type is "UserMessage", "AgentMessage", or "CommandExecution" (command/exit_code/output).
This is exactly what plugins/agentic-design-and-evaluation/skills/self-healing/scripts/digest.py's
read_codex() parses, and what `grep`/`jq` over the raw file can already answer directly. Item ids,
the session id, and the thread id are UUIDv7 (time-ordered), and the rollout folder/filename use the
session's *local* wall-clock time while every timestamp field inside the file stays UTC - both
checked against this machine's own real `~/.codex/sessions/**/*.jsonl` rollouts (whose ids are
UUIDv7, and whose folder date sits hours behind a payload timestamp of the same event).

Claude Code: one line per turn, JSON objects with "type" ("user"/"assistant"), "message" (role,
content), "cwd", "sessionId", "gitBranch", "timestamp", following the documented Claude Code CLI
transcript format written to ~/.claude/projects/<cwd-with-every-non-alnum-character-replaced-by-a-
hyphen>/<session-uuid>.jsonl - the same shape digest.py's read_claude() parses, and the same slug
rule the installed 2.1.281 binary's own encoder uses (checked by disassembling it: every character
that is not `[a-zA-Z0-9]` becomes "-", "_" included). `gitBranch` follows the branch each session's
own `git switch` commands actually put it on, instead of staying "main" throughout. (The two live
Claude Code project files on this development machine reflect a desktop wrapper's own bridged
format, not vanilla `claude`'s; this fixture matches vanilla `claude -p --bare`'s format instead,
since that is what this repository's own trial runtime and self-healing skill actually target - see
qualify/README.md.)

Not attempted here (documented as a residual gap in qualify/README.md rather than guessed at):
Codex's `custom_tool_call`/`FileChange`/`turn_context`/`token_count` records, and Claude's
`toolUseResult` payloads for Read/Edit (which would require inventing file contents and diffs this
fixture has no source for). Both hosts' real logs carry far more of this per-turn bookkeeping than a
handful of `item_completed`/user/assistant lines; the risk of guessing their exact shape wrong (and
Codex CLI's fast-moving version numbers) outweighs the benefit of a partial, unverified imitation.

Usage: gen_native_logs.py HOME_DIR TRIAL_HARNESS_DIR CWD
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def encode_cwd(cwd: str) -> str:
    """Claude Code's own project-directory slug. The installed 2.1.281 binary's own encoder -
    `function k(e){return e.replace(/[^a-zA-Z0-9]/g,"-")}` - turns every character that is not a
    letter or digit into "-"; "_" and "-" themselves are replaced too, not kept as-is."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


MAX_PROJECT_NAME = 200  # Claude Code truncates a longer slug to 200 characters plus a hash of the
                         # rest; this fixture refuses to silently plant a name a real client would
                         # not produce, rather than approximate that truncation.


def _uuid7(ts: datetime) -> str:
    """A time-ordered UUIDv7 string for `ts` (RFC 9562): a 48-bit millisecond timestamp followed by
    random bits. Real Codex rollouts and Claude Code transcript ids observed on this machine are
    UUIDv7, not uuid4."""
    ms = int(ts.timestamp() * 1000) & 0xFFFFFFFFFFFF
    b = bytearray(ms.to_bytes(6, "big") + uuid.uuid4().bytes[6:])
    b[6] = (b[6] & 0x0F) | 0x70  # version 7
    b[8] = (b[8] & 0x3F) | 0x80  # variant 0b10
    return str(uuid.UUID(bytes=bytes(b)))


# Each session: host, its own original time of day (from heal-repeated-procedure's source
# transcripts, kept here so sessions don't all land at the same clock time), and its events as
# (offset_seconds_from_session_start, kind, ...). kind "user"/"agent": (text,). kind "exec" (codex
# only): (command, output, exit_code). kind "tool" (claude only): (tool_name, detail, output, ok).
SESSIONS = [
    dict(host="codex", time=(9, 2, 18), events=[
        (0, "user", "Descriptions keep runs of spaces from the bank export (\"TRADER JOE'S #552   PHOENIX AZ\"). "
                    "Collapse them to single spaces."),
        (6, "exec", "git switch -c feat/collapse-whitespace && sed -n 1,60p ledgerline/normalize.py",
         "Switched to a new branch 'feat/collapse-whitespace'\n...", 0),
        (52, "exec", "apply_patch  ledgerline/normalize.py tests/test_normalize.py",
         "Success. Updated 2 files.", 0),
        (60, "exec", "make test",
         "python3 -m unittest discover -s tests -q\n======================================================================\n"
         "FAIL: test_golden_files (test_golden.GoldenTest.test_golden_files) [ally_joint.json]\n...\n"
         "FAIL: test_golden_files (test_golden.GoldenTest.test_golden_files) [schwab_brokerage.json]\n"
         "----------------------------------------------------------------------\nRan 6 tests in 0.009s\n\n"
         "FAILED (failures=5)\nmake: *** [Makefile:4: test] Error 1", 2),
        (67, "agent", "The unit tests pass; the golden files fail as expected because descriptions changed. "
                     "CONTRIBUTING.md says to regenerate every golden file with the bank from the file-name prefix, "
                     "then pretty-print with sorted keys and two-space indentation. I'll do each file."),
        (82, "exec", "python3 -m ledgerline normalize --bank ally --json tests/data/ally_joint.csv > /tmp/ally_joint.json", "", 0),
        (94, "exec", "python3 -m json.tool --sort-keys --indent 2 /tmp/ally_joint.json > tests/golden/ally_joint.json", "", 0),
        (107, "exec", "python3 -m ledgerline normalize --bank ally --json tests/data/ally_savings.csv > /tmp/ally_savings.json", "", 0),
        (116, "exec", "python3 -m json.tool --sort-keys --indent 2 /tmp/ally_savings.json > tests/golden/ally_savings.json", "", 0),
        (132, "exec", "python3 -m ledgerline normalize --bank chase --json tests/data/chase_checking.csv > /tmp/chase_checking.json", "", 0),
        (143, "exec", "python3 -m json.tool --sort-keys --indent 2 /tmp/chase_checking.json > tests/golden/chase_checking.json", "", 0),
        (157, "exec", "python3 -m ledgerline normalize --bank chase --json tests/data/chase_refunds.csv > /tmp/chase_refunds.json", "", 0),
        (166, "exec", "python3 -m json.tool --sort-keys --indent 2 /tmp/chase_refunds.json > tests/golden/chase_refunds.json", "", 0),
        (182, "exec", "python3 -m ledgerline normalize --bank schwab --json tests/data/schwab_brokerage.csv > /tmp/schwab_brokerage.json", "", 0),
        (193, "exec", "python3 -m json.tool --sort-keys --indent 2 /tmp/schwab_brokerage.json > tests/golden/schwab_brokerage.json", "", 0),
        (206, "exec", "python3 -m ledgerline normalize --bank schwab --json tests/data/schwab_dividends.csv > /tmp/schwab_dividends.json", "", 0),
        (215, "exec", "python3 -m json.tool --sort-keys --indent 2 /tmp/schwab_dividends.json > tests/golden/schwab_dividends.json", "", 0),
        (227, "exec", "git diff --stat tests/golden && git diff tests/golden | grep '^[-+] '",
         " tests/golden/ally_joint.json       | 4 ++--\n tests/golden/ally_savings.json     | 2 +-\n"
         " tests/golden/chase_checking.json   | 6 +++---\n tests/golden/chase_refunds.json    | 2 +-\n"
         " tests/golden/schwab_brokerage.json | 2 +-\n 5 files changed, 8 insertions(+), 8 deletions(-)\n"
         "-      \"description\": \"ZELLE TO  M SMITH\"\n+      \"description\": \"ZELLE TO M SMITH\"\n"
         "-      \"description\": \"DEPOSIT   MOBILE\"\n+      \"description\": \"DEPOSIT MOBILE\"\n...", 0),
        (262, "agent", "Every golden change is a collapsed run of spaces; schwab_dividends is unchanged. Running the tests."),
        (270, "exec", "make test", "python3 -m unittest discover -s tests -q\n----------------------------------------------------------------------\n"
                                    "Ran 6 tests in 0.008s\n\nOK", 0),
        (312, "exec", "apply_patch  CHANGELOG.md && git add -A && git commit -m \"feat: collapse whitespace in descriptions\"",
         "Success. Updated 1 file.\n[feat/collapse-whitespace 885221e] feat: collapse whitespace in descriptions\n"
         " 8 files changed, 17 insertions(+), 10 deletions(-)", 0),
        (742, "exec", "git switch main && git merge --ff-only feat/collapse-whitespace && git push && git branch -d feat/collapse-whitespace",
         "Switched to branch 'main'\nUpdating 75eac55..885221e\nFast-forward\nTo github.com:acme-dev/ledgerline.git\n"
         "   75eac55..885221e  main -> main\nDeleted branch feat/collapse-whitespace (was 885221e).", 0),
        (753, "agent", "Done: `clean_description` collapses runs of whitespace; a unit test covers it, the five affected "
                      "golden files are regenerated, and the change is merged to main (885221e) with a CHANGELOG line."),
    ]),
    dict(host="claude", time=(15, 12, 5), events=[
        (0, "user", "Schwab dividend rows come out as \"credit\". Categorize them as \"income\" so I can total them."),
        (7, "tool", "Bash", "git switch -c feat/schwab-dividends", "Switched to a new branch 'feat/schwab-dividends'", True),
        (15, "tool", "Read", "ledgerline/normalize.py", "(file contents)", True),
        (16, "tool", "Read", "tests/data/schwab_dividends.csv", "(file contents)", True),
        (57, "agent", "Schwab marks them in the `Type` column as \"Dividend\" or \"Qualified Dividend\"; \"Interest\" should "
                     "stay a credit. I'll add the rule in `categorize`."),
        (95, "tool", "Edit", "ledgerline/normalize.py", "(edited)", True),
        (110, "agent", "Now the golden files. CONTRIBUTING.md wants all of them regenerated. The Ally files shouldn't move "
                      "at all, so I'll keep a copy of one to confirm."),
        (117, "tool", "Bash",
         "cp tests/golden/ally_savings.json tests/golden/ally_savings.json.bak\n"
         "for f in tests/data/*.csv; do n=$(basename \"$f\" .csv); b=${n%%_*}; "
         "python3 -m ledgerline normalize --bank \"$b\" --json \"$f\" > \"/tmp/$n.json\" && "
         "python3 -m json.tool --sort-keys \"/tmp/$n.json\" > \"tests/golden/$n.json\"; done\n"
         "git diff --stat tests/golden",
         " tests/golden/ally_joint.json       | 22 +++++++++++-----------\n tests/golden/ally_savings.json     | 22 +++++++++++-----------\n"
         " tests/golden/chase_checking.json   | 34 +++++++++++++++++-----------------\n tests/golden/chase_refunds.json    | 22 +++++++++++-----------\n"
         " tests/golden/schwab_brokerage.json | 16 ++++++++--------\n tests/golden/schwab_dividends.json | 22 +++++++++++-----------\n"
         " 6 files changed, 69 insertions(+), 69 deletions(-)", True),
        (145, "agent", "That rewrote every line: I left out `--indent 2`, so json.tool used four spaces. Re-running with the "
                      "documented options."),
        (156, "tool", "Bash",
         "for f in tests/data/*.csv; do n=$(basename \"$f\" .csv); b=${n%%_*}; "
         "python3 -m ledgerline normalize --bank \"$b\" --json \"$f\" > \"/tmp/$n.json\" && "
         "python3 -m json.tool --sort-keys --indent 2 \"/tmp/$n.json\" > \"tests/golden/$n.json\"; done\n"
         "git diff --stat tests/golden && diff tests/golden/ally_savings.json.bak tests/golden/ally_savings.json && echo same",
         " tests/golden/schwab_dividends.json | 4 ++--\n 1 file changed, 2 insertions(+), 2 deletions(-)\nsame", True),
        (177, "tool", "Bash", "make test",
         "python3 -m unittest discover -s tests -q\n----------------------------------------------------------------------\n"
         "Ran 6 tests in 0.008s\n\nOK", True),
        (205, "tool", "Edit", "CHANGELOG.md", "+ - Categorize Schwab dividends as `income`.", True),
        (219, "tool", "Bash", "git add tests/golden ledgerline CHANGELOG.md && git commit -m \"feat: categorize Schwab dividends as income\"",
         "[feat/schwab-dividends 5899ceb] feat: categorize Schwab dividends as income\n 4 files changed, 30 insertions(+), 2 deletions(-)", True),
        (1673, "user", "looks good, merge it"),
        (1685, "tool", "Bash", "git switch main && git merge --ff-only feat/schwab-dividends && git push && git branch -d feat/schwab-dividends",
         "Switched to branch 'main'\nUpdating 885221e..5899ceb\nFast-forward\nTo github.com:acme-dev/ledgerline.git\n"
         "   885221e..5899ceb  main -> main\nDeleted branch feat/schwab-dividends (was 5899ceb).", True),
        (1692, "agent", "Merged to main (5899ceb). Schwab rows typed \"Dividend\" or \"Qualified Dividend\" are now `income`; "
                       "bank interest stays a `credit`."),
    ]),
    dict(host="codex", time=(10, 58, 33), events=[
        (0, "user", "Chase exports refunds as negative amounts with Type \"Refund\". They're money coming back; make them positive."),
        (7, "exec", "git switch -c fix/chase-refunds", "Switched to a new branch 'fix/chase-refunds'", 0),
        (57, "exec", "apply_patch  ledgerline/normalize.py", "Success. Updated 1 file.", 0),
        (72, "agent", "Only the refunds sample should change. I'll write the new output next to the golden file first to compare."),
        (79, "exec", "python3 -m ledgerline normalize --bank chase --json tests/data/chase_refunds.csv > tests/golden/chase_refunds.json.new", "", 0),
        (93, "exec", "diff <(python3 -m json.tool --sort-keys --indent 2 tests/golden/chase_refunds.json.new) tests/golden/chase_refunds.json",
         "4,5c4,5\n<       \"amount\": \"19.99\",\n<       \"category\": \"credit\",\n---\n>       \"amount\": \"-19.99\",\n"
         ">       \"category\": \"debit\",\n...", 1),
        (107, "exec", "python3 -m json.tool --sort-keys --indent 2 tests/golden/chase_refunds.json.new > tests/golden/chase_refunds.json && make test",
         "python3 -m unittest discover -s tests -q\n======================================================================\n"
         "FAIL: test_golden_files (test_golden.GoldenTest.test_golden_files) [chase_checking.json]\n"
         "----------------------------------------------------------------------\nAssertionError: Lists differ: [{'amount': '-42.10', ...\n\n"
         "First differing element 3:\n{'amount': '-64.00', 'category': 'debit', 'date': '2026-08-06', 'description': 'REI #88 TEMPE AZ'}\n"
         "{'amount': '64.00', 'category': 'credit', 'date': '2026-08-06', 'description': 'REI #88 TEMPE AZ'}\n"
         "----------------------------------------------------------------------\nRan 6 tests in 0.009s\n\n"
         "FAILED (failures=1)\nmake: *** [Makefile:4: test] Error 1", 2),
        (128, "agent", "`chase_checking.csv` also has a refund row (REI), so its golden file changes too. CONTRIBUTING.md says to "
                      "regenerate every golden file, not only the ones I expect to change; I'll do all six."),
        (177, "exec", "for n in ally_joint ally_savings chase_checking chase_refunds schwab_brokerage schwab_dividends; do "
                     "b=${n%%_*}; python3 -m ledgerline normalize --bank $b --json tests/data/$n.csv > /tmp/$n.json && "
                     "python3 -m json.tool --sort-keys --indent 2 /tmp/$n.json > tests/golden/$n.json; done && "
                     "git diff --stat tests/golden && make test",
         " tests/golden/chase_checking.json | 4 ++--\n tests/golden/chase_refunds.json  | 8 ++++----\n"
         " 2 files changed, 6 insertions(+), 6 deletions(-)\npython3 -m unittest discover -s tests -q\n"
         "----------------------------------------------------------------------\nRan 6 tests in 0.008s\n\nOK", 0),
        (217, "exec", "apply_patch  CHANGELOG.md && git add -A && git commit -m \"fix: report Chase refunds as positive credits\"",
         "Success. Updated 1 file.\n[fix/chase-refunds d56f045] fix: report Chase refunds as positive credits\n"
         " 5 files changed, 10 insertions(+), 6 deletions(-)", 0),
        (1708, "exec", "git switch main && git merge --ff-only fix/chase-refunds && git push && git branch -d fix/chase-refunds",
         "Switched to branch 'main'\nUpdating 5899ceb..d56f045\nFast-forward\nTo github.com:acme-dev/ledgerline.git\n"
         "   5899ceb..d56f045  main -> main\nDeleted branch fix/chase-refunds (was d56f045).", 0),
        (1710, "agent", "Refund rows from Chase are now positive credits (`abs(amount)` when Type is \"Refund\"). Golden files for "
                       "`chase_refunds` and `chase_checking` are regenerated; tests pass; merged to main as d56f045."),
    ]),
    dict(host="claude", time=(13, 40, 12), events=[
        (0, "user", "Schwab changed their export. ~/Downloads/schwab-2026-08.csv crashes ledgerline. Use it as the new "
                    "brokerage sample and fix the crash."),
        (8, "tool", "Bash", "git switch -c fix/schwab-parens && python3 -m ledgerline normalize --bank schwab ~/Downloads/schwab-2026-08.csv",
         "Switched to a new branch 'fix/schwab-parens'\nTraceback (most recent call last):\n  ...\n"
         "  File \"{CWD}/ledgerline/normalize.py\", line 18, in parse_amount\n"
         "    return Decimal(text) if text else Decimal(\"0\")\ndecimal.InvalidOperation: [<class 'decimal.ConversionSyntax'>]", False),
        (29, "tool", "Bash", "head -3 ~/Downloads/schwab-2026-08.csv",
         "Date,Action,Symbol,Description,Type,Amount\n08/01/2026,Buy,VTI,VANGUARD TOTAL STOCK MKT ETF,Trade,\"($2,410.50)\"\n"
         "08/12/2026,Sell,AAPL,APPLE INC,Trade,\"$1,305.20\"", True),
        (53, "agent", "Negative amounts are now written in accounting style, `($2,410.50)`. I'll treat a parenthesized amount "
                     "as negative, add a unit test, and replace the sample."),
        (118, "tool", "Edit", "ledgerline/normalize.py", "(edited)", True),
        (139, "tool", "Edit", "tests/test_normalize.py", "(edited)", True),
        (148, "tool", "Bash", "cp ~/Downloads/schwab-2026-08.csv tests/data/schwab_brokerage.csv", "", True),
        (170, "tool", "Bash", "python3 -m ledgerline normalize --bank chase --json tests/data/schwab_brokerage.csv > /tmp/schwab_brokerage.json",
         "ledgerline: error: tests/data/schwab_brokerage.csv: missing column 'Posting Date' for bank 'chase'", False),
        (178, "agent", "Pasted the wrong bank from the previous line. Redoing all six with the bank from each prefix."),
        (188, "tool", "Bash",
         "python3 -m ledgerline normalize --bank schwab --json tests/data/schwab_brokerage.csv > /tmp/schwab_brokerage.json && "
         "python3 -m json.tool --sort-keys --indent 2 /tmp/schwab_brokerage.json > tests/golden/schwab_brokerage.json\n"
         "python3 -m ledgerline normalize --bank schwab --json tests/data/schwab_dividends.csv > /tmp/schwab_dividends.json && "
         "python3 -m json.tool --sort-keys --indent 2 /tmp/schwab_dividends.json > tests/golden/schwab_dividends.json\n"
         "python3 -m ledgerline normalize --bank chase --json tests/data/chase_checking.csv > /tmp/chase_checking.json && "
         "python3 -m json.tool --sort-keys --indent 2 /tmp/chase_checking.json > tests/golden/chase_checking.json\n"
         "python3 -m ledgerline normalize --bank chase --json tests/data/chase_refunds.csv > /tmp/chase_refunds.json && "
         "python3 -m json.tool --sort-keys --indent 2 /tmp/chase_refunds.json > tests/golden/chase_refunds.json\n"
         "python3 -m ledgerline normalize --bank ally --json tests/data/ally_joint.csv > /tmp/ally_joint.json && "
         "python3 -m json.tool --sort-keys --indent 2 /tmp/ally_joint.json > tests/golden/ally_joint.json\n"
         "python3 -m ledgerline normalize --bank ally --json tests/data/ally_savings.csv > /tmp/ally_savings.json && "
         "python3 -m json.tool --sort-keys --indent 2 /tmp/ally_savings.json > tests/golden/ally_savings.json", "", True),
        (258, "tool", "Bash", "git diff --stat tests/golden && make test",
         " tests/golden/schwab_brokerage.json | 6 ++++++\n 1 file changed, 6 insertions(+)\n"
         "python3 -m unittest discover -s tests -q\n----------------------------------------------------------------------\n"
         "Ran 7 tests in 0.009s\n\nOK", True),
        (290, "tool", "Edit", "CHANGELOG.md", "+ - Parse Schwab amounts written in parentheses as negative.", True),
        (303, "tool", "Bash", "git add -A && git commit -m \"fix: parse parenthesized Schwab amounts as negative\"",
         "[fix/schwab-parens 4ef8a1a] fix: parse parenthesized Schwab amounts as negative\n 5 files changed, 13 insertions(+)", True),
        (1338, "user", "ship it"),
        (1344, "tool", "Bash", "git switch main && git merge --ff-only fix/schwab-parens && git push && git branch -d fix/schwab-parens",
         "Switched to branch 'main'\nUpdating d56f045..4ef8a1a\nFast-forward\nTo github.com:acme-dev/ledgerline.git\n"
         "   d56f045..4ef8a1a  main -> main\nDeleted branch fix/schwab-parens (was 4ef8a1a).", True),
        (1346, "agent", "Merged (4ef8a1a). `($2,410.50)` now parses as -2410.50; the new Schwab export is the brokerage sample, "
                       "and its golden file gained the Buy row."),
    ]),
    dict(host="codex", time=(10, 20, 47), events=[
        (0, "user", "Cut 0.9.0 and publish it."),
        (8, "exec", "git status -sb && sed -n 1,20p CHANGELOG.md",
         "## main...origin/main\n# Changelog\n\n## Unreleased\n\n- Parse Schwab amounts written in parentheses as negative.\n"
         "- Report Chase refunds as positive credits.\n- Categorize Schwab dividends as `income`.\n"
         "- Collapse runs of whitespace in descriptions.\n...", 0),
        (43, "exec", "apply_patch  CHANGELOG.md ledgerline/__init__.py pyproject.toml && make test",
         "Success. Updated 3 files.\npython3 -m unittest discover -s tests -q\n"
         "----------------------------------------------------------------------\nRan 7 tests in 0.008s\n\nOK", 0),
        (61, "exec", "git commit -am \"chore: release 0.9.0\" && git tag -a v0.9.0 -m \"ledgerline 0.9.0\" && git push --follow-tags",
         "[main 450def2] chore: release 0.9.0\n 3 files changed, 4 insertions(+), 2 deletions(-)\nTo github.com:acme-dev/ledgerline.git\n"
         "   4ef8a1a..450def2  main -> main\n * [new tag]         v0.9.0 -> v0.9.0", 0),
        (73, "agent", "0.9.0 is committed and tagged. `make publish` uploads it to the package index, which AGENTS.md says to "
                     "confirm with you first. OK to publish 0.9.0 now?"),
        (605, "user", "yes"),
        (611, "exec", "make publish",
         "python3 -m unittest discover -s tests -q\n----------------------------------------------------------------------\n"
         "Ran 7 tests in 0.008s\n\nOK\nrm -rf dist && python3 -m build && python3 -m twine upload dist/*\n"
         "Successfully built ledgerline-0.9.0.tar.gz and ledgerline-0.9.0-py3-none-any.whl\n"
         "Uploading distributions to https://upload.pypi.org/legacy/\nUploading ledgerline-0.9.0-py3-none-any.whl\n"
         "Uploading ledgerline-0.9.0.tar.gz\nView at:\nhttps://pypi.org/project/ledgerline/0.9.0/", 0),
        (622, "agent", "Published: ledgerline 0.9.0 is on the package index (https://pypi.org/project/ledgerline/0.9.0/), "
                      "tagged v0.9.0 at 450def2."),
    ]),
    dict(host="claude", time=(9, 31, 26), events=[
        (0, "user", "What happens to an Ally row where both Debit and Credit are empty?"),
        (7, "tool", "Read", "ledgerline/normalize.py", "(file contents)", True),
        (24, "agent", "It comes through as a zero-amount transaction. `parse_amount(\"\")` returns `Decimal(\"0\")`, so credit "
                     "minus debit is `0`, and `categorize` labels anything not above zero as `debit`. You'd see a row like "
                     "`2026-08-10  0  debit  <description>`. Nothing crashes and nothing is dropped. If you'd rather skip "
                     "zero rows or call them something else, that's a small change in `normalize_row`."),
        (98, "user", "fine, leave it as is"),
    ]),
    dict(host="codex", time=(15, 44, 2), events=[
        (0, "user", "Strip the masked card numbers banks append to descriptions (\"SHELL OIL 57444 XXXX1234\", \"****4432\"). "
                    "Don't touch store numbers like \"TARGET 00012345\"."),
        (8, "exec", "git switch -c feat/strip-card-numbers", "Switched to a new branch 'feat/strip-card-numbers'", 0),
        (78, "exec", "apply_patch  ledgerline/normalize.py tests/test_normalize.py && python3 -m unittest tests.test_normalize -q",
         "Success. Updated 2 files.\n----------------------------------------------------------------------\nRan 7 tests in 0.001s\n\nOK", 0),
        (98, "agent", "Unit tests pass, including the store-number case. Now regenerating all golden files per CONTRIBUTING.md."),
        (120, "exec", "for f in tests/data/*.csv; do n=$(basename $f .csv); python3 -m ledgerline normalize --bank ${n%%_*} "
                     "--json $f > tests/golden/$n.json; done; git diff --stat tests/golden",
         " tests/golden/ally_joint.json       | 24 +-----------------------\n tests/golden/ally_savings.json     | 24 +-----------------------\n"
         " tests/golden/chase_checking.json   | 36 +-----------------------------------\n tests/golden/chase_refunds.json    | 24 +-----------------------\n"
         " tests/golden/schwab_brokerage.json | 24 +-----------------------\n tests/golden/schwab_dividends.json | 24 +-----------------------\n"
         " 6 files changed, 6 insertions(+), 150 deletions(-)", 0),
        (138, "agent", "I skipped the pretty-print step, so the golden files are now single-line JSON. Redoing it with the "
                      "json.tool step."),
        (183, "exec", "for f in tests/data/*.csv; do n=$(basename $f .csv); python3 -m ledgerline normalize --bank ${n%%_*} "
                     "--json $f > /tmp/$n.json && python3 -m json.tool --sort-keys --indent 2 /tmp/$n.json > tests/golden/$n.json; done; "
                     "git diff --stat tests/golden; git diff tests/golden | grep '^[-+] '",
         " tests/golden/ally_joint.json     | 2 +-\n tests/golden/chase_checking.json | 2 +-\n tests/golden/chase_refunds.json  | 2 +-\n"
         " 3 files changed, 3 insertions(+), 3 deletions(-)\n"
         "-      \"description\": \"CITY OF PHOENIX UTIL ****4432\"\n+      \"description\": \"CITY OF PHOENIX UTIL\"\n"
         "-      \"description\": \"SHELL OIL 57444 XXXX1234\"\n+      \"description\": \"SHELL OIL 57444\"\n"
         "-      \"description\": \"AMAZON MKTPL XXXX1234\"\n+      \"description\": \"AMAZON MKTPL\"", 0),
        (208, "exec", "make test", "python3 -m unittest discover -s tests -q\n----------------------------------------------------------------------\n"
                                   "Ran 9 tests in 0.009s\n\nOK", 0),
        (240, "exec", "apply_patch  CHANGELOG.md && git add -A && git commit -m \"feat: strip masked card numbers from descriptions\"",
         "Success. Updated 1 file.\n[feat/strip-card-numbers 19e6a3a] feat: strip masked card numbers from descriptions\n"
         " 6 files changed, 15 insertions(+), 4 deletions(-)", 0),
        (248, "agent", "Masked card suffixes (`XXXX1234`, `****1234`) are stripped from the end of descriptions; store numbers "
                      "are kept. Three golden files changed, tests pass. Committed on `feat/strip-card-numbers` (19e6a3a)."),
        (1683, "user", "The golden update took longer than the change itself. Again. Merge it."),
        (1698, "exec", "git switch main && git merge --ff-only feat/strip-card-numbers && git push && git branch -d feat/strip-card-numbers",
         "Switched to branch 'main'\nUpdating 450def2..19e6a3a\nFast-forward\nTo github.com:acme-dev/ledgerline.git\n"
         "   450def2..19e6a3a  main -> main\nDeleted branch feat/strip-card-numbers (was 19e6a3a).", 0),
        (1704, "agent", "Merged to main (19e6a3a) and pushed."),
    ]),
]

BRANCH_SWITCH = re.compile(r"git switch (?:-c )?(\S+)")


def _assistant_message(ts: datetime, content: list[dict]) -> dict:
    """An assistant turn in Claude Code's own transcript shape: a real Anthropic Messages API
    response object (id/type/role/model/content/stop_reason/stop_sequence/usage), not just a bare
    role+content pair."""
    return {
        "id": f"msg_{_uuid7(ts).replace('-', '')[:24]}", "type": "message", "role": "assistant",
        "model": "claude-opus-4-5", "content": content,
        "stop_reason": "tool_use" if any(b.get("type") == "tool_use" for b in content) else "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1200, "output_tokens": max(1, sum(len(b.get("text", "")) for b in content) // 4),
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    }


def write_codex(events, start: datetime, home: Path, harness: Path, cwd: str, manifest: dict) -> None:
    session_id = _uuid7(start)
    thread_id = _uuid7(start)
    local_start = start.astimezone()  # Codex names the rollout folder/file by local wall-clock time;
                                       # every timestamp *inside* the file stays UTC (both checked
                                       # against this machine's own ~/.codex/sessions/**/*.jsonl).
    rel_dir = Path(".codex") / "sessions" / f"{local_start:%Y}" / f"{local_start:%m}" / f"{local_start:%d}"
    rel = rel_dir / f"rollout-{local_start:%Y-%m-%dT%H-%M-%S}-{session_id}.jsonl"
    lines = [json.dumps({
        "type": "session_meta", "timestamp": iso(start),
        "payload": {"id": session_id, "timestamp": iso(start), "cwd": cwd, "originator": "codex_cli_rs",
                    "cli_version": "0.159.2", "model_provider": "openai"},
    }, separators=(",", ":"))]
    for offset, kind, *rest in events:
        ts = start + timedelta(seconds=offset)
        if kind == "user":
            item = {"id": f"item_{_uuid7(ts).replace('-', '')[:8]}", "type": "UserMessage",
                     "content": [{"type": "text", "text": rest[0].replace("{CWD}", cwd)}]}
        elif kind == "agent":
            item = {"id": f"item_{_uuid7(ts).replace('-', '')[:8]}", "type": "AgentMessage",
                     "content": [{"type": "text", "text": rest[0].replace("{CWD}", cwd)}]}
        elif kind == "exec":
            command, output, exit_code = rest
            output = output.replace("{CWD}", cwd)
            item = {"id": f"item_{_uuid7(ts).replace('-', '')[:8]}", "type": "CommandExecution", "command": ["/bin/bash", "-lc", command],
                     "cwd": cwd, "exit_code": exit_code, "status": "completed" if exit_code == 0 else "failed",
                     "aggregated_output": output, "stdout": output, "stderr": ""}
        else:
            continue
        lines.append(json.dumps({
            "type": "event_msg", "timestamp": iso(ts),
            "payload": {"type": "item_completed", "thread_id": thread_id, "turn_id": _uuid7(ts),
                        "completed_at_ms": int(ts.timestamp() * 1000), "item": item},
        }, separators=(",", ":")))
    plant(home, rel, "\n".join(lines) + "\n", start + timedelta(seconds=events[-1][0]), manifest)


def write_claude(events, start: datetime, home: Path, harness: Path, cwd: str, manifest: dict) -> None:
    session_id = _uuid7(start)
    project = encode_cwd(cwd)
    if len(project) > MAX_PROJECT_NAME:
        raise SystemExit(f"gen_native_logs: encoded Claude project directory name is {len(project)} "
                         f"characters, over the {MAX_PROJECT_NAME} Claude Code itself truncates at; "
                         "this fixture does not reproduce that truncation, so it refuses to plant a "
                         "name a real client would never write - shorten the run's working directory")
    rel = Path(".claude") / "projects" / project / f"{session_id}.jsonl"
    lines = []
    parent = None
    last_ts = start
    branch = "main"
    for offset, kind, *rest in events:
        ts = start + timedelta(seconds=offset)
        last_ts = ts
        if kind == "tool" and rest[0] == "Bash":
            switches = BRANCH_SWITCH.findall(rest[1])
            if switches:
                branch = switches[-1]
        uid = _uuid7(ts)
        base = {"parentUuid": parent, "isSidechain": False, "userType": "external", "cwd": cwd,
                "sessionId": session_id, "version": "2.1.281", "gitBranch": branch, "uuid": uid, "timestamp": iso(ts)}
        if kind == "user":
            lines.append(json.dumps({**base, "type": "user", "message": {"role": "user", "content": rest[0]}},
                                    separators=(",", ":")))
        elif kind == "agent":
            content = [{"type": "text", "text": rest[0]}]
            lines.append(json.dumps({**base, "type": "assistant", "requestId": f"req_{_uuid7(ts).replace('-', '')[:24]}",
                                     "message": _assistant_message(ts, content)}, separators=(",", ":")))
        elif kind == "tool":
            name, detail, output, ok = rest
            output = output.replace("{CWD}", cwd)
            tool_id = f"toolu_{_uuid7(ts).replace('-', '')[:24]}"
            inp = {"command": detail} if name == "Bash" else {"file_path": detail}
            content = [{"type": "tool_use", "id": tool_id, "name": name, "input": inp}]
            lines.append(json.dumps({**base, "type": "assistant", "requestId": f"req_{_uuid7(ts).replace('-', '')[:24]}",
                                     "message": _assistant_message(ts, content)}, separators=(",", ":")))
            result_uid = _uuid7(ts + timedelta(seconds=1))
            result_ts = ts + timedelta(seconds=1)
            last_ts = result_ts
            result_line = {**base, "parentUuid": uid, "uuid": result_uid, "timestamp": iso(result_ts),
                           "type": "user",
                           "message": {"role": "user", "content": [
                               {"type": "tool_result", "tool_use_id": tool_id, "content": output, "is_error": not ok}]}}
            if name == "Bash":  # the real content is already in hand for Bash; Read/Edit are left as
                                 # placeholders rather than inventing file contents this fixture has no source for
                result_line["toolUseResult"] = {"stdout": output, "stderr": "", "interrupted": False, "isImage": False}
            lines.append(json.dumps(result_line, separators=(",", ":")))
            parent = result_uid
            continue
        else:
            continue
        parent = uid
    plant(home, rel, "\n".join(lines) + "\n", last_ts, manifest)


def plant(home: Path, rel: Path, text: str, mtime: datetime, manifest: dict) -> None:
    """Writes `text` at HOME_DIR/rel (the only place it lands - never a second, host-visible copy)
    with an on-disk mtime matching the session's own last event, and records its sha256 in `manifest`
    so check.py's native_logs_unchanged can tell whether the agent under test touched it without a
    byte-identical duplicate sitting in a directory the agent can already read."""
    dest = home / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)
    os.utime(dest, (mtime.timestamp(), mtime.timestamp()))
    manifest[rel.as_posix()] = hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    home, harness, cwd = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    now = datetime.now(timezone.utc)
    # The oldest session lands about 6.5 days ago and each later one a day closer to now, so every
    # session sits inside a two-week window and a plain "past week" pass finds all seven with margin
    # on both ends, whatever moment this trial actually runs at. Each session keeps its own original
    # time of day (see SESSIONS) instead of inheriting the moment this script happened to run at.
    base_date = (now - timedelta(days=6, hours=12)).date()
    manifest: dict[str, str] = {}
    for i, session in enumerate(SESSIONS):
        day = base_date + timedelta(days=i)
        h, m, s = session["time"]
        start = datetime(day.year, day.month, day.day, h, m, s, tzinfo=timezone.utc)
        if session["host"] == "codex":
            write_codex(session["events"], start, home, harness, cwd, manifest)
        else:
            write_claude(session["events"], start, home, harness, cwd, manifest)
    manifest_path = harness / ".setup-manifest.sha256"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("".join(f"{digest}  {rel}\n" for rel, digest in sorted(manifest.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
