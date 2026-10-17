"""Read-only package observations; no native CLI calls or target imports."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HOST_DIRECTORY = re.compile(r"\.(.+)-plugin")


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
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
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


def host_directories(directory):
    """The `.<host>-plugin` directories directly inside a directory, as (host, path), sorted by host."""
    found = []
    for path in directory.iterdir():
        match = HOST_DIRECTORY.fullmatch(path.name)
        if match and path.is_dir():
            found.append((match.group(1), path))
    return sorted(found)


def parent_catalogs(root):
    """The nearest `.<host>-plugin/marketplace.json` of each host in the parent directories."""
    found = {}
    for parent in list(root.resolve().parents)[:5]:
        try:
            for host, directory in host_directories(parent):
                if host not in found and (directory / "marketplace.json").is_file():
                    found[host] = directory / "marketplace.json"
        except OSError:
            continue  # a parent that cannot be read holds no catalog to compare
    return [found[host] for host in sorted(found)]


def cached_copies(name):
    """Installed candidates `plugins/cache/*/<name>` under hidden home directories and `*_HOME` directories."""
    homes = []
    try:
        homes.extend(path for path in Path.home().iterdir() if path.name.startswith("."))
    except (OSError, RuntimeError):
        pass  # no readable home directory
    homes.extend(Path(value) for key, value in os.environ.items() if key.endswith("_HOME") and value)
    found = set()
    for home in homes:
        try:
            found.update(path.resolve() for path in (home / "plugins/cache").glob(f"*/{name}") if path.is_dir())
        except (OSError, RuntimeError):
            continue  # a cache that cannot be read holds no copy to compare
    return found


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
    for host, directory in host_directories(root):
        path = directory / "plugin.json"
        if path.is_file():
            obj = read_object(path)
            manifests[host] = {k: string_field(obj, k, path) for k in ("version", "description", "license")}
    if not manifests:
        observe("no_manifest", ".<host>-plugin/plugin.json",
                "no .<host>-plugin directory directly under the plugin directory holds a plugin.json")
        unchecked.append("manifest-fields")
    for key in ("version", "description", "license"):
        declared = [(host, fields[key]) for host, fields in manifests.items() if fields[key]]
        for host, value in declared[1:]:
            first, expected = declared[0]
            if value != expected:
                fact = (f"{first} and {host} manifests expose different description text" if key == "description"
                        else f"{first} manifest says {expected}, {host} manifest says {value}")
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
                            f"the {host} package description differs from this skill's frontmatter description")

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

    catalogs = [Path(args.marketplace)] if args.marketplace else parent_catalogs(root)
    catalogs = [c for c in catalogs if c.is_file()]
    if not catalogs:
        unchecked.append("catalog")
    tracking_checked = False
    for marketplace in catalogs:
        catalog = read_object(marketplace)
        entries = catalog.get("plugins")
        if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
            raise ValueError(f"cannot collect plugins array in {marketplace}")
        matches = [e for e in entries if e.get("name") == name]
        if len(matches) > 1:
            raise ValueError(f"ambiguous duplicate catalog entries for {name} in {marketplace}")
        if not matches:
            observe("not_published", name, f"no entry in {marketplace}", "repo-overlay")
            continue
        if not tracking_checked:
            tracking_checked = True
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
        if not version:
            observe("catalog_no_version", name,
                    f"catalog entry in {marketplace} declares no version to compare against", "repo-overlay")
        else:
            for host, fields in manifests.items():
                if fields["version"] and version != fields["version"]:
                    observe("catalog_version_difference", "version",
                            f"catalog {marketplace} says {version}, {host} manifest says {fields['version']}", "repo-overlay")

    installed = Path(args.installed) if args.installed else None
    if installed is None:
        # These are filesystem candidates, never evidence of active host selection.
        candidates = cached_copies(name)
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
