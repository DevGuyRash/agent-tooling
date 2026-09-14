#!/usr/bin/env sh
set -eu
REPO_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    echo 'error: audit-plugins requires Python 3 to validate reporter output' >&2
    exit 2
fi
exec python3 - "$REPO_ROOT" "$@" <<'PY'
"""Repository selection and strict report consumption, not semantic grading."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

repo = Path(sys.argv.pop(1))
parser = argparse.ArgumentParser(prog='audit-plugins.sh', description=(
    'Run optional structural reporters on all plugins or named plugins. '
    'A valid report establishes only its declared observations, not overall quality. '
    'Malformed output or a failed invocation is a tool failure, never a pass.'))
parser.add_argument('--errors-only', action='store_true', help='omit observations')
parser.add_argument('plugins', nargs='*')
args = parser.parse_args()
reporters = repo / 'plugins/agentic-design-and-evaluation/skills/skill-auditor/scripts'
if not reporters.is_dir():
    parser.error(f'reporters not found at {reporters}')
targets = args.plugins or sorted(p.name for p in (repo / 'plugins').iterdir() if p.is_dir())
errors = observations = checked = failures = 0


def validate_report(data, name, status):
    if not isinstance(data, dict) or data.get('script') != name:
        raise ValueError('missing or mismatched report identity')
    for count, items in (('error_count', 'errors'), ('observation_count', 'observations')):
        if type(data.get(count)) is not int or data[count] < 0 or not isinstance(data.get(items), list):
            raise ValueError(f'invalid {count} or {items}')
        if data[count] != len(data[items]):
            raise ValueError(f'{count} disagrees with {items}')
        for item in data[items]:
            if not isinstance(item, dict) or any(not isinstance(item.get(k), str) for k in ('code', 'subject', 'fact')):
                raise ValueError(f'malformed item in {items}')
            if 'source' in item and not isinstance(item['source'], str):
                raise ValueError('invalid observation source')
    if status != (1 if data['error_count'] else 0):
        raise ValueError('process status contradicts the report')


def report(name, target, label):
    global errors, observations, failures
    proc = None
    try:
        proc = subprocess.run(['sh', str(reporters / (name + '.sh')), str(target), '--format', 'json'],
                              capture_output=True, text=True)
        if proc.returncode not in (0, 1):
            raise ValueError(f'process exited {proc.returncode}')
        data = json.loads(proc.stdout)
        validate_report(data, name, proc.returncode)
    except (OSError, ValueError) as exc:
        failures += 1
        print(f'  {label}: tool failure: {exc}')
        if proc is not None:
            for line in (proc.stdout + proc.stderr).splitlines():
                print('    ' + line)
        return
    errors += data['error_count']
    observations += data['observation_count']
    entries = [(item, 'ERROR ') for item in data['errors']]
    if not args.errors_only:
        entries += [(item, '') for item in data['observations']]
    if entries:
        print('  ' + label)
    for item, prefix in entries:
        print(f"    {prefix}{item['code']}: {item['subject']}\n      {item['fact']}")
        if 'source' in item:
            print('      source: ' + item['source'])


for name in targets:
    target = repo / 'plugins' / name
    # Deletions and renames appear in the changed-file input too.
    if not target.is_dir():
        print(f'{name}: no such plugin directory — skipped')
        continue
    print(name)
    checked += 1
    report('plugin_check', target, f'{name}: plugin_check')
    for skill in sorted((target / 'skills').glob('*/SKILL.md')):
        for helper in ('frontmatter_check', 'reference_check', 'script_sanity'):
            report(helper, skill.parent, f'{name}/{skill.parent.name}: {helper}')

print(f'\nplugins checked: {checked}\nerrors: {errors}\nobservations: {observations}\ntool failures: {failures}')
if failures or errors:
    print(f'result: {errors} structural error(s), {failures} tool failure(s); required evidence is incomplete where a tool failed')
    raise SystemExit(1)
if checked == 0:
    print('result: no existing plugin selected; no structural checks performed')
else:
    print('result: selected structural checks passed')
PY
