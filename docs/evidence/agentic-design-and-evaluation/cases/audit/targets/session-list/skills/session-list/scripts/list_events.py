#!/usr/bin/env python3
import json
from pathlib import Path
import sys

def main():
    if len(sys.argv) != 3:
        print('error: provide INPUT_JSON OUTPUT_TXT', file=sys.stderr)
        return 2
    try:
        settings = json.loads((Path(__file__).resolve().parents[1] / 'references' / 'settings.json').read_text())
        events = json.loads(Path(sys.argv[1]).read_text())
        lines = [f"{settings['prefix']}: {e['title']} — {e['date']}" for e in events if e['status'] == 'confirmed']
        Path(sys.argv[2]).write_text('\n'.join(lines) + ('\n' if lines else ''))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
