"""Read-only package observations; no native CLI calls or target imports."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(f"error: {message}\nhint: use --help; supported formats: text, json", file=sys.stderr)
        raise SystemExit(2)


def read_object(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"ambiguous duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def string_field(value, key, path):
    field = value.get(key, "")
    if not isinstance(field, str):
        raise ValueError(f"cannot collect non-string {key} in {path}")
    return field


def skill_description(path):
    """Bounded scalar reader, not YAML validation; unsupported forms stay unchecked."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return None
    lines = lines[1:lines.index("---", 1)]
    for index, line in enumerate(lines):
        if not line.startswith("description:"):
            continue
        value = line.partition(":")[2].strip()
        if value.startswith('"'):
            try:
                decoded = json.loads(value)
                return decoded if isinstance(decoded, str) else None
            except json.JSONDecodeError:
                return None
        if value.startswith("'"):
            return value[1:-1].replace("''", "'") if value.endswith("'") else None
        if value.startswith(">") or value.startswith("|"):
            if value not in {">", ">-", ">+", "|", "|-", "|+"}:
                return None
            body = []
            for following in lines[index + 1:]:
                if following and not following[0].isspace():
                    break
                body.append(following)
            nonempty = [s for s in body if s.strip()]
            if not nonempty:
                return ""
            indent = len(nonempty[0]) - len(nonempty[0].lstrip())
            if any(s.strip() and len(s) - len(s.lstrip()) != indent for s in body):
                return None
            body = [s[indent:] if s.strip() else "" for s in body]
            if value.startswith(">") and any(not s for s in body):
                return None
            text = (" " if value.startswith(">") else "\n").join(body)
            if value.endswith("-"):
                return text.rstrip("\n")
            if value.endswith("+"):
                return text + "\n"
            return text.rstrip("\n") + "\n"
        if not value or value.startswith(("[", "{", "&", "*", "!", "#")) or " #" in value:
            return None
        return value
    return None


def walk_files(root):
    def failed(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=failed):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_file() and not path.is_symlink():
                yield path


def tree_facts(root):
    """Preserve topology, bytes, executable bits, and link text without following links."""
    facts = []
    pending = [root]
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                facts.append((relative, "L", os.readlink(path)))
            elif path.is_dir():
                facts.append((relative, "D"))
                pending.append(path)
            elif path.is_file():
                facts.append((relative, "F", bool(path.stat().st_mode & 0o111),
                              hashlib.sha256(path.read_bytes()).hexdigest()))
            else:
                facts.append((relative, "O"))
    return sorted(facts)


def collect(args):
    root = Path(args.plugin_directory)
    if not root.is_dir():
        raise ValueError(f"plugin directory not found: {root}")
    name = root.name
    observations = []
    unchecked = []

    def observe(code, subject, fact, source="plugin-fit"):
        observations.append(dict(code=code, subject=subject, fact=fact, source=source))

    manifests = {}
    for host in ("claude", "codex"):
        relative = f".{host}-plugin/plugin.json"
        path = root / relative
        if path.is_file():
            obj = read_object(path)
            manifests[host] = {k: string_field(obj, k, path) for k in ("version", "description", "license")}
        else:
            observe(f"missing_{host}_manifest", relative,
                    f"the file does not exist; this package exposes no {host.title()} manifest at that path")
            unchecked.append(f"{host}-manifest-fields")
    if len(manifests) == 2:
        for key in ("version", "description", "license"):
            a, b = manifests["claude"][key], manifests["codex"][key]
            if a and b and a != b:
                fact = ("claude and codex manifests expose different description text" if key == "description"
                        else f"claude manifest says {a}, codex manifest says {b}")
                observe(f"manifest_{key}_difference", key, fact)

    skills = sorted(p for p in (root / "skills").glob("*/SKILL.md") if p.is_file() and not p.is_symlink())
    if not skills:
        observe("no_skills", "skills", "no SKILL.md was found under the package skills directory")
    if len(skills) == 1:
        description = skill_description(skills[0])
        if description is None:
            unchecked.append(f"skill-{skills[0].parent.name}-description")
        elif description:
            for host, fields in manifests.items():
                if fields["description"] and fields["description"] != description:
                    observe("skill_description_difference", skills[0].parent.name,
                            f"the {host.title()} package description differs from this skill's frontmatter description")

    license_name = next((m["license"] for m in manifests.values() if m["license"]), "")
    if license_name:
        probe = root
        found = False
        for _ in range(5):
            if any((probe / n).is_file() for n in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")):
                found = True
                break
            if probe.parent == probe:
                break
            probe = probe.parent
        if not found:
            observe("license_without_file", license_name,
                    "the manifest declares this license but no LICENSE file was found above the plugin", "repo-overlay")

    marketplace = Path(args.marketplace) if args.marketplace else None
    if marketplace is None:
        for parent in list(root.resolve().parents)[:5]:
            candidate = parent / ".claude-plugin/marketplace.json"
            if candidate.is_file():
                marketplace = candidate
                break
    if marketplace is not None and marketplace.is_file():
        catalog = read_object(marketplace)
        entries = catalog.get("plugins")
        if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
            raise ValueError(f"cannot collect plugins array in {marketplace}")
        matches = [e for e in entries if e.get("name") == name]
        if len(matches) > 1:
            raise ValueError(f"ambiguous duplicate catalog entries for {name}")
        if not matches:
            observe("not_published", name, f"no entry in {marketplace}", "repo-overlay")
        else:
            try:
                proc = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                                      text=True, capture_output=True, timeout=10)
                if proc.returncode == 0:
                    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "."],
                                             text=True, capture_output=True, timeout=10)
                    if tracked.returncode:
                        raise ValueError(f"cannot collect tracked files in {root}")
                    if not tracked.stdout:
                        observe("published_but_untracked", name,
                                "the catalog entry exists but no file under the plugin directory is tracked by git", "repo-overlay")
                else:
                    unchecked.append("tracking")
            except FileNotFoundError:
                unchecked.append("tracking")
            version = string_field(matches[0], "version", marketplace)
            source_version = manifests.get("claude", {}).get("version", "")
            if not version:
                observe("catalog_no_version", name, "catalog entry declares no version to compare against", "repo-overlay")
            elif source_version and version != source_version:
                observe("catalog_version_difference", "version",
                        f"catalog says {version}, Claude manifest says {source_version}", "repo-overlay")
    else:
        unchecked.append("catalog")

    installed = Path(args.installed) if args.installed else None
    if installed is None:
        candidates = set()
        # These are filesystem candidates, never evidence of active host selection.
        roots = [Path.home() / ".claude/plugins/cache",
                 Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "plugins/cache"]
        for base in roots:
            if base.is_dir():
                candidates.update(p for p in base.glob(f"*/{name}") if p.is_dir())
        if len(candidates) == 1:
            installed = candidates.pop()
        elif candidates:
            unchecked.append("install-multiple-host-caches-use---installed")
    if installed is not None and installed.is_dir():
        installed_files = list(walk_files(installed))
        for source in skills:
            slug = source.parent.name
            matches = [p for p in installed_files if p.name == "SKILL.md" and p.parent.name == slug]
            if len(matches) > 1:
                unchecked.append(f"install-{slug}-multiple-copies-use---installed")
            elif len(matches) == 1:
                if tree_facts(source.parent) != tree_facts(matches[0].parent):
                    observe("install_drift", slug,
                            "the installed skill tree differs from the repository in content, topology, link destinations, or executable-file availability")
            else:
                unchecked.append(f"install-{slug}-not-found")
        unchecked.append("install-package-surfaces-outside-skills")
    elif not any(s.startswith("install-") for s in unchecked):
        unchecked.append("install")
    return dict(script="plugin_check", plugin_dir=args.plugin_directory, plugin=name, skills=len(skills),
                unchecked=",".join(unchecked), error_count=0, errors=[],
                observation_count=len(observations), observations=observations)


def main():
    parser = Parser(prog="plugin_check.sh", description=(
        "Report package, catalog, and installed-tree facts; observations are not policy verdicts. "
        "Requires Python 3. Surfaces not located remain unchecked. Exit 0: report produced; "
        "exit 2: unusable arguments, input, or failed collection."))
    parser.add_argument("plugin_directory")
    parser.add_argument("--marketplace")
    parser.add_argument("--installed")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    try:
        result = collect(args)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    if args.format == "json":
        print(json.dumps(result, separators=(",", ":"), ensure_ascii=True))
    else:
        print(f"REPORT plugin_check\nplugin_dir={result['plugin_dir']}\nplugin={result['plugin']}\nskills={result['skills']}")
        if result["unchecked"]:
            print("unchecked=" + result["unchecked"])
        print(f"errors=0\nobservations={result['observation_count']}")
        for observation in result["observations"]:
            print(f"{observation['code']}: {observation['subject']}\n  {observation['fact']}\n  source: {observation['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
