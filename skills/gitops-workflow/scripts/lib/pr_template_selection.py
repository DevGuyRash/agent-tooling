#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


def main() -> int:
    requested = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = sys.argv[2] if len(sys.argv) > 2 else ""

    try:
        data = json.loads(payload or "{}")
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"invalid template discovery json: {exc}\n")
        return 2

    templates = data.get("templates")
    if not isinstance(templates, list):
        sys.stderr.write("template discovery payload missing templates array\n")
        return 2

    selected = None
    logical_templates: dict[str, dict[str, object]] = {}
    for template in templates:
        path = template.get("path")
        if not path:
            continue
        existing = logical_templates.get(path)
        if existing is None or (existing.get("source") != "local" and template.get("source") == "local"):
            logical_templates[path] = template

    deduped_templates = list(logical_templates.values())

    if requested:
        exact = [template for template in templates if template.get("id") == requested]
        if exact:
            selected = exact[0]
        else:
            path_matches = [template for template in deduped_templates if template.get("path") == requested]
            if len(path_matches) == 1:
                selected = path_matches[0]
            else:
                sys.stderr.write(f"template id not found in discovered templates: {requested}\n")
                return 3
    elif len(deduped_templates) == 1:
        selected = deduped_templates[0]
    else:
        for template in deduped_templates:
            if template.get("source") == "local":
                selected = template
                break

    selected_id = selected.get("id", "") if selected else ""
    selected_source = selected.get("source", "") if selected else ""

    print(len(deduped_templates))
    print(selected_id)
    print(selected_source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
