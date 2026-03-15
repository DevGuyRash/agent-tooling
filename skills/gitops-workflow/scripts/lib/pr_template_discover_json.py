#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    records_path = Path(sys.argv[1])
    repo = sys.argv[2]
    ref = sys.argv[3]
    templates = []
    for line in records_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        source, path, template_id = line.split("\t")
        entry = {
            "id": template_id,
            "path": path,
            "source": source,
        }
        if source == "remote" and repo:
            entry["repo"] = repo
            entry["ref"] = ref
        templates.append(entry)

    print(json.dumps({"repo": repo, "ref": ref, "templates": templates}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
