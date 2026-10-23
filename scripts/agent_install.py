"""Own Codex custom-agent copies without overwriting user-managed agents."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


RECEIPT = '.plugin-portability.json'
LOCK = '.plugin-portability.lock'
OWNED_PREFIX = 'plugin-port-'


class AgentInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentPlan:
    root: Path
    before: dict[str, bytes]
    changes: dict[str, bytes | None]
    config_digest: str | None = None


def owned_path(path: Path) -> bool:
    return path.name in {RECEIPT, LOCK} or path.name.startswith(OWNED_PREFIX)


def snapshot(root: Path) -> dict[str, bytes]:
    if root.is_symlink():
        raise AgentInstallError(f'agent directory must not be a symlink: {root}')
    if not root.exists():
        return {}
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            if owned_path(path):
                raise AgentInstallError(f'agent path must not be a symlink: {path}')
            # A user's own agent linked in by a dotfile manager: read it to avoid name collisions, never write it.
            # A link that resolves to no regular file is skipped, as Codex discovery skips it.
            if path.suffix == '.toml' and path.is_file():
                result[path.relative_to(root).as_posix()] = path.read_bytes()
            continue
        if path.is_dir():
            continue
        if path.suffix != '.toml' and path.name != RECEIPT:
            continue
        if not path.is_file():
            raise AgentInstallError(f'agent path is not a regular file: {path}')
        result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def existing_agent_name(content: bytes) -> str | None:
    """The name Codex would register for an agent file this installer does not own, or None when Codex would ignore it."""
    try:
        value = tomllib.loads(content.decode('utf-8')).get('name')
    except (ValueError, UnicodeDecodeError):
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def agent_name(content: bytes, path: str) -> str:
    try:
        value = tomllib.loads(content.decode('utf-8')).get('name')
    except (ValueError, UnicodeDecodeError) as exc:
        raise AgentInstallError(f'cannot parse agent {path}: {exc}') from exc
    if not isinstance(value, str) or not value.strip():
        raise AgentInstallError(f'agent has no name: {path}')
    return value.strip()


def legacy_agents(home: Path) -> tuple[set[str], str | None]:
    path = home / 'config.toml'
    if not path.exists():
        return set(), None
    raw = path.read_bytes()
    try:
        agents = tomllib.loads(raw.decode('utf-8')).get('agents', {})
    except (ValueError, UnicodeDecodeError) as exc:
        raise AgentInstallError(f'cannot parse Codex configuration: {path}') from exc
    if not isinstance(agents, dict):
        raise AgentInstallError(f'invalid agents configuration: {path}')
    return {name for name, value in agents.items() if isinstance(value, dict)}, digest(raw)


def document_filename(path: Path) -> str:
    return hashlib.sha256(path.as_posix().encode()).hexdigest()[:16] + '.toml'


def plan(home: Path, owner: str, documents: Mapping[str, str]) -> AgentPlan:
    return plan_many(home, {owner: documents})


def _plan(root: Path, before: dict[str, bytes], owner: str, documents: Mapping[str, str]) -> AgentPlan:
    try:
        receipt = json.loads(before.get(RECEIPT, b'{"schema_version":1,"owners":{}}'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AgentInstallError(f'invalid agent receipt: {root / RECEIPT}') from exc
    if not isinstance(receipt, dict) or receipt.get('schema_version') != 1 or not isinstance(receipt.get('owners'), dict):
        raise AgentInstallError(f'invalid agent receipt: {root / RECEIPT}')
    owners = receipt['owners']
    claimed = set()
    for identity, files in owners.items():
        if not isinstance(identity, str) or not isinstance(files, dict):
            raise AgentInstallError('invalid agent receipt owner')
        for filename, sha in files.items():
            if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith('.toml') or not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
                raise AgentInstallError('invalid agent receipt file')
            expected_prefix = 'plugin-port-' + hashlib.sha256(identity.encode()).hexdigest()[:16] + '-'
            if not filename.startswith(expected_prefix):
                raise AgentInstallError('agent receipt file does not belong to its owner')
            if filename in claimed:
                raise AgentInstallError(f'duplicate agent ownership: {filename}')
            claimed.add(filename)
    previous = owners.get(owner, {})
    for filename, sha in previous.items():
        if filename in before and digest(before[filename]) != sha:
            raise AgentInstallError(f'owned agent was modified; preserve or move it before retrying: {root / filename}')
    prefix = OWNED_PREFIX + hashlib.sha256(owner.encode()).hexdigest()[:16] + '-'
    desired = {}
    names = set()
    for filename, content in documents.items():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.toml', filename):
            raise AgentInstallError(f'invalid target agent filename: {filename}')
        target = prefix + filename
        raw = content.encode('utf-8')
        name = agent_name(raw, filename)
        if name in names:
            raise AgentInstallError(f'duplicate desired agent name: {name}')
        names.add(name)
        if target in before and target not in previous:
            raise AgentInstallError(f'agent destination already exists without ownership: {root / target}')
        desired[target] = raw
    for filename, content in before.items():
        if filename.endswith('.toml') and filename not in previous:
            name = existing_agent_name(content)
            if name is not None and name in names:
                raise AgentInstallError(f'agent name {name!r} already exists: {root / filename}')
    changes: dict[str, bytes | None] = {filename: None for filename in previous if filename in before and filename not in desired}
    changes.update({filename: content for filename, content in desired.items() if before.get(filename) != content})
    if desired:
        owners[owner] = {filename: digest(content) for filename, content in desired.items()}
    else:
        owners.pop(owner, None)
    new_receipt = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    if (owners or RECEIPT in before) and before.get(RECEIPT) != new_receipt:
        changes[RECEIPT] = new_receipt
    return AgentPlan(root, before, changes)


def plan_many(home: Path, owners: Mapping[str, Mapping[str, str]]) -> AgentPlan:
    root = home / 'agents'
    if root.is_symlink() and not any(owners.values()):
        # Nothing to project, and nothing was ever written through a linked directory: leave it alone.
        return AgentPlan(root, {}, {})
    before = snapshot(root)
    after = dict(before)
    legacy_names, config_digest = legacy_agents(home)
    for documents in owners.values():
        for filename, content in documents.items():
            name = agent_name(content.encode('utf-8'), filename)
            if name in legacy_names:
                raise AgentInstallError(f'agent name {name!r} already exists in {home / "config.toml"}')
    for owner, documents in owners.items():
        for filename, content in _plan(root, after, owner, documents).changes.items():
            if content is None:
                after.pop(filename, None)
            else:
                after[filename] = content
    changes = {name: after.get(name) for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    if RECEIPT in changes:
        changes[RECEIPT] = changes.pop(RECEIPT)
    if changes:
        try:
            import fcntl
        except ImportError as exc:
            raise AgentInstallError('agent installation requires a POSIX host with fcntl locking; conversion is still supported') from exc
    return AgentPlan(root, before, changes, config_digest)


def write_atomic(path: Path, content: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def apply(planned: AgentPlan) -> None:
    if not planned.changes:
        return
    planned.root.mkdir(parents=True, exist_ok=True)
    lock = planned.root / LOCK
    if lock.is_symlink():
        raise AgentInstallError(f'agent lock must not be a symlink: {lock}')
    import fcntl
    with lock.open('a+b') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if snapshot(planned.root) != planned.before or legacy_agents(planned.root.parent)[1] != planned.config_digest:
            raise AgentInstallError('agent files changed since planning; retry without overwriting them')
        completed = []
        try:
            for filename, content in planned.changes.items():
                path = planned.root / filename
                if content is None:
                    path.unlink()
                else:
                    write_atomic(path, content)
                completed.append(filename)
        except BaseException:
            for filename in reversed(completed):
                path = planned.root / filename
                if filename in planned.before:
                    write_atomic(path, planned.before[filename])
                else:
                    path.unlink(missing_ok=True)
            raise


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    if __package__:
        from . import plugin_port
    else:
        import plugin_port
    parser = argparse.ArgumentParser(description='Project plugin agents into Codex custom-agent discovery without changing the plugin marketplace.')
    parser.add_argument('package', nargs='?')
    parser.add_argument('--owner', required=True, help='Stable plugin@marketplace ownership identifier.')
    parser.add_argument('--namespace', help='Registered name prefix; defaults to the plugin component of --owner.')
    parser.add_argument('--codex-home', default=os.environ.get('CODEX_HOME') or str(Path.home() / '.codex'))
    parser.add_argument('--agent-model', action='append', default=[], metavar='SOURCE=TARGET')
    parser.add_argument('--remove', action='store_true', help='Remove only unchanged custom-agent copies owned by this identifier.')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if bool(args.package) == args.remove:
        parser.error('provide a package to install, or --remove without a package')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+', args.owner):
        parser.error('--owner must be a plugin@marketplace identifier')
    try:
        documents = {}
        if args.package:
            package = plugin_port.detect_plugin(Path(args.package))
            for document in plugin_port.agent_documents(package.root, 'codex', plugin_port.agent_model_map(args.agent_model), namespace=args.namespace or args.owner.split('@', 1)[0]):
                documents[document_filename(document.path)] = document.content
                for warning in document.warnings:
                    print(f'agent-install: {warning}', file=sys.stderr)
        planned = plan(Path(args.codex_home).expanduser(), args.owner, documents)
        count = len(planned.changes) - (RECEIPT in planned.changes)
        if not args.dry_run:
            apply(planned)
        print(json.dumps({'owner': args.owner, 'dry_run': args.dry_run, 'agent_file_changes': count, 'agent_directory': str(planned.root)}))
        return 0
    except (AgentInstallError, plugin_port.PluginPortError, OSError) as exc:
        print(f'agent-install: error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
