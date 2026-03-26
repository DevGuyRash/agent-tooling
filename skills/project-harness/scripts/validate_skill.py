#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import py_compile
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

MANAGED_REQUIRED_PREFIXES = (
    "assets/just-",
    "assets/workflow-",
)


def fail(message: str, hint: str | None = None, code: int = 1) -> int:
    sys.stderr.write(f"error: {message}\n")
    if hint:
        sys.stderr.write(f"hint: {hint}\n")
    return code


def read_frontmatter(skill_md: Path) -> tuple[dict, str]:
    text = skill_md.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("SKILL.md is missing YAML frontmatter delimiters")
    raw = parts[1]
    lines = raw.splitlines()
    frontmatter: dict[str, object] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("  "):
            i += 1
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            i += 1
            continue
        if value in {">-", "|-", ">", "|"}:
            i += 1
            collected: list[str] = []
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    collected.append("")
                    i += 1
                    continue
                if nxt.startswith("  "):
                    collected.append(nxt.strip())
                    i += 1
                    continue
                break
            frontmatter[key] = " ".join(part for part in (item.strip() for item in collected) if part)
            continue
        if value == "":
            nested: dict[str, str] = {}
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.startswith("  "):
                    break
                nkey, _, nvalue = nxt.strip().partition(":")
                nested[nkey.strip()] = nvalue.strip().strip('"')
                i += 1
            frontmatter[key] = nested
            continue
        frontmatter[key] = value.strip('"')
        i += 1
    body = parts[2]
    return frontmatter, body


def has_crlf(path: Path) -> bool:
    return b"\r\n" in path.read_bytes()


def extract_skill_root_refs(text: str) -> list[str]:
    return re.findall(r"<skills-file-root>/([^`\s)]+)", text)


def display_name_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def run_smoke(skill_root: Path) -> tuple[bool, str]:
    script = skill_root / "scripts" / "selftest_project_harness.py"
    if not script.exists():
        return False, "missing smoke-test script"
    proc = subprocess.run(
        [sys.executable, str(script), "--skill-root", str(skill_root)],
        cwd=str(skill_root),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stdout + "\n" + proc.stderr).strip()
        return False, detail or "smoke tests failed"
    return True, proc.stdout.strip() or "smoke tests passed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a project-harness style skill package.")
    parser.add_argument("skill_root")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.skill_root).resolve()
    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        return fail("SKILL.md not found", "pass the path to the skill root")

    front, _body = read_frontmatter(skill_md)
    errors: list[str] = []
    warnings: list[str] = []
    smoke: dict[str, object] | None = None

    name = front.get("name", "")
    description = front.get("description", "")
    if not isinstance(name, str) or not name:
        errors.append("missing required frontmatter field: name")
    if not isinstance(description, str) or not description:
        errors.append("missing required frontmatter field: description")

    if isinstance(name, str):
        if len(name) > 64:
            errors.append("frontmatter name exceeds 64 characters")
        expected_display_name = display_name_from_slug(root.name)
        if name != expected_display_name:
            errors.append(
                f"frontmatter name '{name}' does not match display name '{expected_display_name}' derived from directory name '{root.name}'"
            )

    if isinstance(description, str) and len(description) > 1024:
        errors.append("description exceeds 1024 characters")

    skill_text = skill_md.read_text(encoding="utf-8")
    skill_lines = skill_text.splitlines()
    if len(skill_lines) > 500:
        warnings.append("SKILL.md exceeds 500 lines; progressive disclosure is at risk")

    ref_dir = root / "references"
    ref_files = sorted(ref_dir.glob("*.md")) if ref_dir.exists() else []
    for ref in ref_files:
        lines = ref.read_text(encoding="utf-8").splitlines()
        if len(lines) > 300:
            warnings.append(f"reference file exceeds 300 lines: {ref.name}")

    referenced_paths: set[str] = set()
    for md in [skill_md, *ref_files]:
        for rel in extract_skill_root_refs(md.read_text(encoding="utf-8")):
            referenced_paths.add(rel)
    for rel in sorted(referenced_paths):
        if not (root / rel).exists():
            errors.append(f"missing referenced path: <skills-file-root>/{rel}")

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".md", ".py", ".sh", ".yml", ".yaml", ".toml", ".tpl"} and has_crlf(path):
            errors.append(f"CRLF line endings found: {path.relative_to(root).as_posix()}")

    scripts_dir = root / "scripts"
    python_scripts = sorted(scripts_dir.glob("*.py")) if scripts_dir.exists() else []
    for script in python_scripts:
        try:
            py_compile.compile(str(script), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"python compile failed: {script.relative_to(root).as_posix()}: {exc.msg}")
        mode = script.stat().st_mode
        if not (mode & stat.S_IXUSR):
            warnings.append(f"script is not executable: {script.name}")

    for path in sorted(root.rglob("*.tpl")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel.startswith(MANAGED_REQUIRED_PREFIXES) and "# project-harness: managed-file" not in text:
            warnings.append(f"template is missing managed marker: {rel}")

    if (root / "scripts" / "project_harness.py.bak").exists():
        warnings.append("remove backup file before shipping: scripts/project_harness.py.bak")
    for cache_dir in list(root.rglob("__pycache__")):
        shutil.rmtree(cache_dir, ignore_errors=True)

    if args.smoke:
        ok, detail = run_smoke(root)
        smoke = {"passed": ok, "detail": detail}
        if not ok:
            errors.append("smoke tests failed")

    payload = {
        "skill_root": str(root),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "name": name,
        "description_length": len(description) if isinstance(description, str) else None,
        "skill_lines": len(skill_lines),
    }
    if smoke is not None:
        payload["smoke"] = smoke
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
