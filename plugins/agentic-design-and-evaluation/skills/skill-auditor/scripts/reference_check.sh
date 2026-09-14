#!/usr/bin/env sh
set -eu
if ! command -v python3 >/dev/null 2>&1; then
    echo 'error: reference_check requires Python 3' >&2
    echo 'hint: use a host with Python 3, or inspect the declared paths directly' >&2
    exit 2
fi
exec python3 - "$@" <<'PY'
"""Bounded Markdown file-reference reporter; no target mutation or imports."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"error: {message}\nhint: use --help for supported arguments", file=sys.stderr)
        raise SystemExit(2)


parser = Parser(prog="reference_check.sh", description=(
    "Report literal local .md file references in SKILL.md and its references/ documents. "
    "Resolve paths from the declaring file; <skills-file-root> resolves from the skill root. "
    "Supports inline Markdown links, link definitions, and code paths containing a slash. "
    "Quoted blocks, fenced examples, dynamic and ambiguous paths are unverified observations. "
    "Remote URLs and anchors are not checked. Exit: 0 no structural errors, 1 missing files, "
    "2 unusable invocation or input; this is not a quality verdict."))
parser.add_argument("skill_directory")
parser.add_argument("--format", choices=("text", "json"), default="text")
args = parser.parse_args()
root = Path(args.skill_directory).resolve()
if not (root / "SKILL.md").is_file():
    parser.error(f"SKILL.md not found in {args.skill_directory}")

# Deliberately bounded syntax, not a complete Markdown parser. Do not extract a
# matching suffix from a longer expression: ../sibling/references/a.md is one path.
LINK = re.compile(r'\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+["\'][^\n]*["\'])?\s*\)')
DEFINITION = re.compile(r'^\s{0,3}\[[^\]]+\]:\s*(<[^>\n]+>|\S+)')
CODE = re.compile(r'`([^`\n]+)`')
BARE = re.compile(r'(?<![\w/.$<>{}*-])(?:<skills-file-root>/|(?:\.\.?/)*)(?:[\w.-]+/)*references/[^\s`\)\]\"\']+\.md(?:#[\w.-]*)?')
errors = []
observations = []
seen = set()


def add(bucket, code, subject, fact, source=None):
    key = (code, subject, fact)
    if key in seen:
        return
    seen.add(key)
    item = dict(code=code, subject=subject, fact=fact)
    if source:
        item["source"] = source
    bucket.append(item)


def candidates(doc):
    fence = None
    for line in doc.read_text(encoding="utf-8").splitlines():
        fence_match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        quoted = fence is not None or bool(re.match(r'^\s*>', line))
        if fence_match:
            token = fence_match.group(1)
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1]:
                fence = None
            continue
        spans = [(m.start(), m.end(), m.group(1)) for m in LINK.finditer(line)]
        definition = DEFINITION.match(line)
        if definition:
            spans.append((definition.start(), definition.end(), definition.group(1)))
        spans.extend((m.start(), m.end(), m.group(1)) for m in CODE.finditer(line)
                     if '/' in m.group(1))
        # Legacy bare references remain observable, without losing a prefix.
        spans.extend((m.start(), m.end(), m.group()) for m in BARE.finditer(line)
                     if not any(a <= m.start() < b for a, b, _ in spans))
        for _, _, raw in sorted(spans):
            if '.md' in raw:
                yield raw, quoted


def resolve(doc, raw, quoted):
    value = raw.strip()
    if value.startswith('<') and value.endswith('>'):
        value = value[1:-1]
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', value) or value.startswith('//'):
        return None
    if value.startswith('#'):
        return None
    subject = value if doc.name == 'SKILL.md' else f'{doc.relative_to(root)}: {value}'
    host_prefix = value.startswith('<skills-file-root>/')
    local = value[len('<skills-file-root>/'):] if host_prefix else value
    # Commands, placeholders, globs, and unsupported destinations must not be
    # converted into missing-file claims by matching a convenient substring.
    if quoted or re.search(r'[$*{}<>\\\n]', local) or ' ' in local.strip('<>') or local.startswith('/'):
        add(observations, 'unverified_reference', subject,
            'example, dynamic, absolute, or ambiguous path; existence was not established')
        return None
    parsed = urlsplit(local)
    path = unquote(parsed.path)
    if not path.endswith('.md'):
        return None
    if host_prefix:
        add(observations, 'nonportable_reference_prefix', subject,
            'the path uses a host placeholder; verify support on the intended host', 'open-standard')
    target = ((root if host_prefix else doc.parent) / path).resolve()
    if not target.is_file():
        add(errors, 'missing_reference_file', subject,
            f'{doc.relative_to(root)} declares this literal path; no file exists there')
    return target


try:
    refs = sorted((root / 'references').rglob('*.md')) if (root / 'references').is_dir() else []
    direct = set()
    for doc in [root / 'SKILL.md', *refs]:
        links = sorted(set(candidates(doc)))
        resolved = {target for raw, quoted in links if (target := resolve(doc, raw, quoted)) is not None}
        if doc == root / 'SKILL.md':
            direct = resolved
        elif links:
            add(observations, 'nested_reference_link', str(doc.relative_to(root)),
                'this reference declares another Markdown resource; applicability requires judgment', 'SKILL.md')
    for ref in refs:
        if ref.resolve() not in direct:
            add(observations, 'unlinked_reference', str(ref.relative_to(root)),
                'the file exists but no supported literal path in SKILL.md points at it', 'SKILL.md')
except (OSError, UnicodeError, ValueError) as exc:
    parser.error(str(exc))

result = dict(script='reference_check', skill_dir=args.skill_directory,
              linked_references=len(direct), active_references=len(refs),
              error_count=len(errors), errors=errors,
              observation_count=len(observations), observations=observations)
if args.format == 'json':
    print(json.dumps(result, separators=(',', ':'), ensure_ascii=False))
else:
    print(f'REPORT reference_check\nskill_dir={args.skill_directory}\nlinked_references={len(direct)}\nactive_references={len(refs)}\nerrors={len(errors)}\nobservations={len(observations)}')
    for items, prefix in ((errors, 'ERROR '), (observations, '')):
        for item in items:
            print(f"{prefix}{item['code']}: {item['subject']}\n  {item['fact']}")
            if 'source' in item:
                print(f"  source: {item['source']}")
sys.exit(1 if errors else 0)
PY
