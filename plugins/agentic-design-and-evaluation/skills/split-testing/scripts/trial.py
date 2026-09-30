#!/usr/bin/env python3
"""Run repeated, isolated, interleaved trials of alternatives and summarize them.

A plan names arms (the alternatives: an executor plus its model and instructions) and
scenarios (a task with an optional fixture, fake tools, and checks). Every arm runs every
scenario `repeats` times, each run in its own fresh home and working directory, in an
interleaved order. Each run keeps its native record (events, final message, the executor's
session files) and a result with deterministic check outcomes and an optional blind judge
verdict. Summaries report per-scenario pass counts with 95% Wilson intervals.

    trial.py run PLAN.json [--out DIR] [--jobs N] [--repeats K] [--only A,B] [--arms A,B]
                           [--retry-invalid] [--sandbox confined|none]
    trial.py recheck DIR [--rejudge] [--judge JSON] [--sandbox confined|none]
                                  (re-score finished runs after a check or judge question changes)
    trial.py derive DIR --scenario S --artifact PATH --consumer SCENARIO_DIR --plan PLAN.json
                                  (second stage: artifacts from an earlier run become arms)
    trial.py pairwise DIR --arms A,B [--judge-model MODEL] [--jobs N]
                                  (blind head-to-head judging of two arms' matched runs, both orders)
    trial.py summarize DIR [--json] [--baseline ARM]
    trial.py report DIR [--out FILE] [--baseline ARM]
                                  (one JSON document - plan, runs, aggregates, pairwise - for a visualizer)
    trial.py models [--match GLOB] [--latest] [--base-url URL] [--env-file F] [--api-key-var V]
                                  (model IDs an endpoint serves)

Plan (paths relative to the plan file):

    {"name": "kernel-screen", "repeats": 5, "seed": 1, "sandbox": "confined", "baseline": "none",
     "arms": {"none":   {"executor": "codex", "model": "${TRIAL_CODEX_MODEL}", "effort": "high"},
              "kernel": {"executor": "codex", "model": "${TRIAL_CODEX_MODEL}", "effort": "high",
                         "instructions": "arms/kernel.md"}},
     "scenarios": ["../scenarios/blocked-deploy"],
     "judge": {"executor": "codex", "model": "${TRIAL_CODEX_MODEL}", "effort": "high"}}

Settings fields (model, effort, base_url, binary, env_file, api_key_var) expand ${VAR} and
${VAR:-default}; a model "latest:GLOB" resolves to the newest numeric version the endpoint serves,
once per run directory: a rerun into the directory reuses the model it recorded for that spec. Every
run records its arm's model settings and instructions digest (executors read a copy of the
instructions kept in the run directory) and the judge that scored it, and a rerun that would mix
them in one directory is refused. "sandbox" (plan level, or --sandbox) sets the default confinement
for every scenario that does not name its own; "baseline" (or --baseline on summarize) names the arm
other arms' cost and timing are compared against as a percentage.

Scenario directory:

    scenario.json  {"prompt": "...", "followups": ["..."], "timeout_s": 900,
                    "required": ["check_name", ...], "artifact": "relative/path",
                    "judge": {"question": "...", "pass_when": "..."}, "judge_role": "...",
                    "judge_required": true}
                   ("sandbox" is optional here - confined/none/a Codex-native mode; omitted, a scenario
                    takes the plan's default, which is how --sandbox none reaches every scenario at once)
    fixture/       copied into the working directory
    setup.sh       optional; runs in the working directory before the agent starts
    bin/           optional fake tools, prepended to PATH (scenario.json "bin" can list other
                   directories relative to the scenario); tools may append JSON lines to
                   "$TRIAL_HARNESS/calls.jsonl"
    check.py       def check(run) -> {name: bool | number | str}
                   optional def judge_context(run) -> str (evidence shown to the judge)

Executors: "codex" (codex exec in a private CODEX_HOME holding only the model provider
settings plus the arm's instructions as AGENTS.md), "claude" (claude -p --bare with the
arm's instructions appended to the system prompt), "command" (a shell command, for
non-agent comparisons and for testing this runner), and "artifact" (no model call: the
arm's own "artifact" - a file or directory, relative to the plan, such as a business plan,
a recipe, or a design - is the alternative itself, copied into the run as the output to
judge). Any executor's scenario can also name its own "artifact" (a path the executor was
asked to write, relative to its working directory), which becomes the judged output in its
place. Runs live outside any git repository
so executors cannot discover unrelated project instructions. By default ("sandbox":
"confined") codex, claude, and command runs execute inside bubblewrap with the host
read-only, the user's home hidden, and only the run directory writable; their environment
is an explicit allowlist (PATH, a throwaway HOME and TMPDIR, locale and terminal identity,
an arm's "pass_env" names, and the one API key variable the arm uses), never the parent
environment. Confinement needs bubblewrap; where it is missing, a "confined" scenario
refuses to start rather than running unconfined, unless "sandbox": "none" (plan level or
--sandbox none) says so explicitly.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import contextlib
import datetime as dt
import errno
import fnmatch
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import shutil
import shlex
import signal
import socket
import stat
import statistics
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

try:
    import fcntl  # POSIX only; absent, _lock falls back to the O_EXCL/pid scheme below
except ImportError:
    fcntl = None

try:
    import tomllib  # 3.11+; used only to read an existing ~/.codex/config.toml (see _provider_block), lazily
except ImportError:  # macOS's own /usr/bin/python3 is often older than 3.11
    tomllib = None

DEFAULT_OUT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "agent-trials"
CODEX_HOME_SRC = Path(os.environ.get("TRIAL_CODEX_SOURCE_HOME", Path.home() / ".codex"))
# System-wide tool locations a confined process (or a check running agent code) can rely on, whatever the
# scenario's own tools and PATH additions are: Linux's, and Homebrew's two install prefixes on macOS (Intel
# and Apple Silicon) - never a user- or version-manager-specific path, which belongs in a scenario's own
# "bin" or an arm's "readable"/"pass_env" instead.
SYSTEM_PATH = ["/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin", "/usr/local/sbin",
              "/opt/homebrew/bin", "/opt/homebrew/sbin"]


class TrialError(Exception):
    pass


# ---------------------------------------------------------------- plan loading

def load_plan(path: Path, repeats: int | None, only: list[str] | None, arms: list[str] | None,
              stored: dict | None = None, query: bool = True):
    """The plan with the selected arms and scenarios. `stored` is the run directory's recorded plan, which
    answers latest: specs it resolved before; with query False no endpoint is asked (see resolve_arm)."""
    plan = json.loads(path.read_text())
    base = path.parent
    plan["repeats"] = repeats or int(plan.get("repeats", 3))
    plan.setdefault("seed", 1)
    plan.setdefault("name", path.stem)
    scenarios = []
    for rel in plan["scenarios"]:
        sdir = (base / rel).resolve()
        spec = json.loads((sdir / "scenario.json").read_text())
        spec["dir"] = str(sdir)
        spec["name"] = spec.get("name", sdir.name)
        if only and spec["name"] not in only:
            continue
        scenarios.append(spec)
    if not scenarios:
        raise TrialError("no scenarios selected")
    selected = {}
    for name, arm in plan["arms"].items():
        if arms and name not in arms:
            continue
        selected[name] = _with_resources(_with_artifact(_with_instructions(
            _check_env_file(resolve_arm(arm, f"arm '{name}'", stored, query, base), f"arm '{name}'"),
            base, f"arm '{name}'"), base, f"arm '{name}'"), base, f"arm '{name}'")
    if not selected:
        raise TrialError("no arms selected; valid arms: " + ", ".join(plan["arms"]))
    plan["arms"] = selected
    plan["scenarios"] = scenarios
    if plan.get("judge") is not None:
        plan["judge"] = _with_resources(_check_env_file(resolve_arm(_check_judge(plan["judge"], "judge"), "judge",
                                                                    stored, query, base), "judge"), base, "judge")
    return plan


def _check_judge(judge, where: str) -> dict:
    if not isinstance(judge, dict) or judge.get("executor") not in ("codex", "claude") or not judge.get("model"):
        raise TrialError(f"{where} must be a JSON object with an executor and a model; valid judge executors: codex, claude")
    return judge


def _check_env_file(arm: dict, where: str) -> dict:
    """An agent executor given an env_file that does not exist would run without its key."""
    if arm.get("executor") in ("codex", "claude") and arm.get("env_file") and not Path(arm["env_file"]).exists():
        raise TrialError(f"{where} env_file {arm['env_file']} does not exist")
    return arm


def _with_instructions(arm: dict, base: Path, where: str) -> dict:
    """Resolve the instructions path and record a digest of its content, which is part of what a run measured."""
    if arm.get("instructions"):
        path = (base / Path(arm["instructions"]).expanduser()).resolve()
        try:
            arm["instructions_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise TrialError(f"{where} instructions {path}: {exc.strerror}") from None
        arm["instructions"] = str(path)
    return arm


def _path_digest(path: Path) -> str:
    """sha256 of a file's bytes, or of every regular file beneath a directory (sorted by relative path,
    each entry's own path and content both hashed) - the same identity guarantee a single file's digest
    gives instructions, extended to an artifact that may be a whole directory."""
    h = hashlib.sha256()
    if path.is_dir():
        for f in sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink()):
            h.update(str(f.relative_to(path)).encode() + b"\0")
            h.update(f.read_bytes())
    else:
        h.update(path.read_bytes())
    return h.hexdigest()


def _with_artifact(arm: dict, base: Path, where: str) -> dict:
    """An "artifact" arm names the alternative itself - a file or directory, relative to the plan, such as
    a business plan, a recipe, or a design - rather than anything the runtime executes. Resolve it and
    record a digest of its content, so a run directory that would mix different content under the same
    arm name is refused, the same guarantee instructions get."""
    if arm.get("executor") != "artifact":
        return arm
    if not arm.get("artifact"):
        raise TrialError(f"{where} is an \"artifact\" executor with no \"artifact\" path")
    path = (base / Path(arm["artifact"]).expanduser()).resolve()
    if not path.exists():
        raise TrialError(f"{where} artifact {path} does not exist")
    try:
        arm["artifact_sha256"] = _path_digest(path)
    except OSError as exc:
        raise TrialError(f"{where} artifact {path}: {exc.strerror}") from None
    arm["artifact"] = str(path)
    return arm


def _with_resources(arm: dict, base: Path, where: str) -> dict:
    """"resources": a map from a path relative to the run's private home to a file or directory relative
    to the plan, copied read-only into that home before the run starts - a skill, a reference doc, or
    anything else an arm's instructions can point the agent at by a fixed path (see trials.md). Each
    source is resolved and digested, like instructions and an artifact, so a run directory that would give
    the same arm name different resource content is refused."""
    res = arm.get("resources")
    if not res:
        return arm
    if not isinstance(res, dict) or not all(isinstance(k, str) for k in res):
        raise TrialError(f"{where} \"resources\" must be an object of {{home-relative path: plan-relative path}}")
    resolved, digests = {}, []
    for rel, src in res.items():
        if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise TrialError(f"{where} resources key {rel!r} must be a relative path inside the home, without \"..\"")
        path = (base / Path(src).expanduser()).resolve()
        if not path.exists():
            raise TrialError(f"{where} resources[{rel!r}] {path} does not exist")
        try:
            digest = _path_digest(path)
        except OSError as exc:
            raise TrialError(f"{where} resources[{rel!r}] {path}: {exc.strerror}") from None
        resolved[rel] = str(path)
        digests.append(f"{rel}\0{digest}")
    arm["resources"] = resolved
    arm["resources_sha256"] = hashlib.sha256("\0".join(sorted(digests)).encode()).hexdigest()
    return arm


# ---------------------------------------------------------------- model selection

SETTINGS_FIELDS = ("model", "effort", "base_url", "binary", "env_file", "api_key_var")
_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_MODELS: dict[tuple, list[str]] = {}
# The listing child's environment beyond PATH: how this host reaches endpoints, never a key.
_NET_ENV = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy", "all_proxy",
            "SSL_CERT_FILE", "SSL_CERT_DIR")


def _expand_env(value: str, where: str) -> str:
    if "${" in _ENV_REF.sub("", value) or any("${" in (m.group(2) or "") for m in _ENV_REF.finditer(value)):
        raise TrialError(f"{where} {value!r}: only ${{VAR}} and ${{VAR:-default}} expand, without nesting")

    def repl(m):
        name, default = m.group(1), m.group(2)
        if os.environ.get(name):
            return os.environ[name]
        if default is not None:
            return default
        raise TrialError(f"{where} uses ${{{name}}}, which is unset or empty; set it or write ${{{name}:-default}}")
    return _ENV_REF.sub(repl, value)


def resolve_arm(arm: dict, where: str, stored: dict | None = None, query: bool = True, base: Path | None = None) -> dict:
    """Expand environment references in an arm's settings and resolve a "latest:GLOB" model. A setting other
    than model that expands to nothing is left unset; an empty model is an error. A spec the run directory
    resolved before (same expanded spec, same endpoint) takes the recorded model, so each spec resolves once
    per directory; with query False only the stored plan and TRIAL_MODELS_FILE answer, and anything else stays
    unresolved. The spec as written is kept as model_spec, and the expanded latest: spec as model_query. A
    relative env_file is relative to `base` (the plan's directory), or to the current directory without one."""
    arm = dict(arm)
    raw = arm.get("model")
    for key in SETTINGS_FIELDS:
        value = arm.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise TrialError(f"{where} {key} must be a string")
        value = _expand_env(value, f"{where} {key}")
        value = value.rstrip("/") if key == "base_url" else value
        if value and key == "env_file":
            arm[key] = str(((base or Path.cwd()) / Path(value).expanduser()).resolve())
        elif value:
            arm[key] = value
        elif key == "model":
            raise TrialError(f"{where} model is empty after expansion")
        else:
            del arm[key]
    model = arm.get("model")
    if model and model.startswith("latest:"):
        arm["model_query"] = model
        known = _stored_answer(stored or {}, arm)
        if known:
            arm["model"] = known
        elif query or os.environ.get("TRIAL_MODELS_FILE"):
            keys = ("base_url", "env_file", "api_key_var") if arm.get("executor") == "claude" else ("env_file", "api_key_var")
            flags = "".join(f" --{k.replace('_', '-')} {shlex.quote(arm[k])}" for k in keys if arm.get(k))
            arm["model"] = latest_model(model[len("latest:"):], available_models(arm, where), where, flags)
    if isinstance(raw, str) and raw != arm.get("model"):
        arm["model_spec"] = raw
    return arm


def _listing(arm: dict):
    """Where an arm's models are listed: its base_url for a Claude arm, the Codex model provider otherwise."""
    return ("claude", arm.get("base_url")) if arm.get("executor") == "claude" else ("provider",)


def _resolution_key(arm: dict) -> str:
    return json.dumps([*_listing(arm), arm["model_query"]])


def _record_resolutions(resolved: dict | None, entries) -> dict:
    """The run directory's resolutions, keyed by endpoint and expanded latest: spec; the first answer stays."""
    resolved = dict(resolved or {})
    for entry in entries:
        model = (entry or {}).get("model") or ""
        if entry and entry.get("model_query") and model and not model.startswith("latest:"):
            resolved.setdefault(_resolution_key(entry), model)
    return resolved


def _stored_answer(stored: dict, arm: dict) -> str | None:
    known = stored.get("resolved", {}).get(_resolution_key(arm))
    if known:
        return known
    for prev in [*stored.get("arms", {}).values(), stored.get("judge") or {}]:
        model = prev.get("model") or ""
        if prev.get("model_query") == arm["model_query"] and _listing(prev) == _listing(arm) and not model.startswith("latest:"):
            return model
    return None


def _version_key(parts: tuple[str, ...]):
    """The numbers a pattern's wildcards matched, compared numerically. From a part's first date stamp on (a
    segment of four or more digits, such as 20250929, 0613, or the 2025 of 2025-08-07), segments only break ties."""
    nums, dates = [], []
    for part in parts:
        dated = False
        for seg in re.split(r"[.-]", part):
            dated = dated or len(seg) >= 4
            digits = seg.lstrip("0")
            (dates if dated else nums).append((len(digits), digits))
    return (tuple(nums), tuple(dates))


def latest_model(pattern: str, ids: list[str], where: str = "model", flags: str = "") -> str:
    """The ID matching PATTERN whose wildcard parts form the highest numeric version. Each * matches a version
    number only (digits joined by '.' or '-'), so variants such as '-thinking' never match."""
    if any(c in pattern for c in "?[]") or pattern.count("*") > 3:
        raise TrialError(f"{where}: latest:{pattern} can use only *, at most three times, each standing for a version number")
    rx = re.compile(r"([0-9]+(?:[.-][0-9]+)*)".join(re.escape(piece) for piece in pattern.split("*")))
    matches = [(m.groups(), i) for i in ids if len(i) <= 256 and (m := rx.fullmatch(i))]
    if not matches:
        raise TrialError(f"{where}: no model matches latest:{pattern}, where each * stands for a version number such as "
                         f"5-5 or 6.1 (name a family sharing a non-numeric suffix by including it after the last *, "
                         f"as in latest:*-preview); list the candidates with "
                         f"`trial.py models --match '{pattern.split('*')[0]}*'{flags}`")
    return max(matches, key=lambda m: _version_key(m[0]))[1]


# Runs in a child process that alone holds the key: the key never follows a redirect, and errors report only
# a status or exception type, never text that could carry a header value.
_LIST_MODELS = """\
import json, os, sys, urllib.error, urllib.parse, urllib.request
url, anthropic = sys.argv[1], sys.argv[2] == 'anthropic'
key = os.environ.get('TRIAL_MODELS_KEY', '')
if sys.argv[3] == 'key' and not key:
    sys.exit('NO_KEY')
if not key.isascii() or '\\r' in key or '\\n' in key:
    sys.exit('BAD_KEY')
ids, after = [], None
try:
    for _ in range(50):
        page = url + ('?' + urllib.parse.urlencode({'limit': 1000, **({'after_id': after} if after else {})}) if anthropic else '')
        req = urllib.request.Request(page, headers={'anthropic-version': '2023-06-01'} if anthropic else {})
        if key:
            req.add_unredirected_header(*(('x-api-key', key) if anthropic else ('Authorization', 'Bearer ' + key)))
        data = json.load(urllib.request.urlopen(req, timeout=20))
        data = data if isinstance(data, dict) else {}
        ids += [m['id'] for m in data.get('data') or [] if isinstance(m, dict) and isinstance(m.get('id'), str)
                and m['id'].isprintable() and not any(c.isspace() for c in m['id'])]
        if not (anthropic and data.get('has_more') and data.get('last_id')) or data['last_id'] == after:
            break
        after = data['last_id']
except urllib.error.HTTPError as exc:
    sys.exit(f'HTTP {exc.code}')
except urllib.error.URLError as exc:
    sys.exit(f'URLError: {exc.reason}')
except Exception as exc:
    sys.exit(type(exc).__name__)
print(json.dumps(ids))
"""


def _default_key_var(executor: str | None) -> str:
    """The key variable name an arm gets when it names none itself: a Claude arm reads ANTHROPIC_API_KEY;
    any other arm reads whatever env_key its Codex model provider config names, or CODEX_API_KEY absent
    that - the variable OpenAI's own docs name for authenticating a non-interactive `codex exec` process
    with no custom model provider configured (most people running Codex against its own default endpoint
    have no `model_providers` block at all, so this is the variable that actually reaches Codex for them;
    `OPENAI_API_KEY` is not read by `codex exec` itself absent a provider config naming it as `env_key`)."""
    return "ANTHROPIC_API_KEY" if executor == "claude" else (_provider_key_var() or "CODEX_API_KEY")


def _env_file_for(arm: dict) -> Path | None:
    """Where an arm's key file is: its own "env_file", or TRIAL_ENV_FILE when it names none. There is no
    default file any more; with neither set, the key is read straight from this process's own environment."""
    ef = arm.get("env_file") or os.environ.get("TRIAL_ENV_FILE")
    return Path(ef).expanduser().resolve() if ef else None


def available_models(arm: dict, where: str = "models") -> list[str]:
    """Model IDs the arm's endpoint serves: a Claude arm asks its base_url (Anthropic format), any other arm
    asks the Codex model provider (OpenAI format). The key (api_key_var, from env_file, TRIAL_ENV_FILE, or
    this process's own environment) is read by a child process only. TRIAL_MODELS_FILE (one ID per line)
    replaces the query."""
    listed = os.environ.get("TRIAL_MODELS_FILE")
    if listed:
        try:
            return [line.strip() for line in Path(listed).read_text().splitlines() if line.strip()]
        except (OSError, UnicodeDecodeError) as exc:
            raise TrialError(f"cannot read TRIAL_MODELS_FILE {listed}: {getattr(exc, 'strerror', None) or exc}") from None
    anthropic = arm.get("executor") == "claude"
    if anthropic:
        if not arm.get("base_url"):
            raise TrialError(f"{where}: a Claude arm's models are listed at its base_url; set base_url or "
                             "TRIAL_MODELS_FILE, or name the model")
        url = arm["base_url"].rstrip("/") + "/v1/models"
    else:
        base_url = _provider_block().get("base_url")
        if not base_url:
            raise TrialError(f"{where}: the Codex config names no model provider with a base_url to list models from; set "
                             "TRIAL_MODELS_FILE (or pass --base-url to `trial.py models`), or name an exact model")
        url = base_url.rstrip("/") + "/models"
    try:
        parts = urllib.parse.urlsplit(url)
        shown = f"{parts.scheme}://{parts.hostname}{f':{parts.port}' if parts.port else ''}{parts.path}"
    except ValueError:
        raise TrialError(f"{where}: cannot parse the endpoint URL") from None
    if parts.scheme not in ("http", "https"):
        raise TrialError(f"{where}: models are listed over http or https, not {shown}")
    if "@" in parts.netloc or parts.query or parts.fragment:
        raise TrialError(f"{where}: {shown} carries credentials, a query, or a fragment; put the key behind env_file and api_key_var")
    env_file = _env_file_for(arm)
    if env_file and not env_file.exists():
        raise TrialError(f"{where}: env_file {env_file} does not exist")
    var = arm.get("api_key_var") or _default_key_var(arm.get("executor"))
    cache = (url, str(env_file) if env_file else "", var)
    if cache not in _MODELS:
        if env_file:
            prefix, direct_env = _key_prefix(env_file, var, "TRIAL_MODELS_KEY"), {}
        else:
            value = os.environ.get(var)
            prefix, direct_env = [], ({"TRIAL_MODELS_KEY": value} if value else {})
        try:
            r = subprocess.run(prefix + [sys.executable, "-I", "-c", _LIST_MODELS, url, "anthropic" if anthropic else "openai",
                                         "key" if (prefix or direct_env) else "none"],
                               env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                                    **{k: v for k, v in os.environ.items() if k in _NET_ENV}, **direct_env},
                               capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            raise TrialError(f"timed out listing models from {shown}") from None
        if r.returncode != 0:
            reason = (r.stderr.strip().splitlines() or ["no response"])[-1]
            source = f" in {env_file}" if env_file else " in the environment"
            if reason == "NO_KEY":
                reason = f"{var} is unset or empty{source}"
            elif reason == "BAD_KEY":
                reason = (f"{var}{source} holds a line break or a non-ASCII character (a CRLF line ending or a pasted "
                          "quote?), which a request header cannot carry")
            elif reason in ("HTTP 401", "HTTP 403") and not prefix and not direct_env:
                reason += (f" (no key was sent: {var} is unset; set it with the arm's env_file, TRIAL_ENV_FILE, "
                          "--env-file for `trial.py models`, or in this process's environment)")
            raise TrialError(f"could not list models from {shown}: {reason}")
        try:
            ids = json.loads(r.stdout)
        except json.JSONDecodeError:
            ids = []
        if not ids:
            raise TrialError(f"{shown} listed no model IDs (expected a JSON object with a data list)")
        _MODELS[cache] = ids
    return _MODELS[cache]


# ---------------------------------------------------------------- run directory

# The settings each result records for its arm ("identity") and for the judge that scored it ("judge_identity");
# results written before those records existed fall back to plan.json's first four.
IDENTITY_FIELDS = ("executor", "model", "effort", "base_url", "instructions_sha256", "artifact_sha256", "command",
                   "allowed_tools", "permission_mode", "resources_sha256")
JUDGE_FIELDS = IDENTITY_FIELDS[:4]


def _effective(ident: dict, judge: bool, confined: bool | None = None) -> dict:
    """A recorded identity with the defaults the executors apply, so writing out a default is no change.
    `confined` is the confinement a Claude identity's own "permission_mode" default would resolve under
    (see run_claude): a claude arm's own record always carries the mode it actually used, but a freshly
    loaded plan's arm does not carry one until an executor runs it, so a rerun's own identity is compared
    against the SAME confinement the record it is being checked against actually ran under - never against
    a fixed guess - or a real change from confined to unconfined (or back) would go undetected precisely
    where it matters most (see _refuse_changes)."""
    ident = {k: v for k, v in ident.items() if v not in (None, "", [])}
    if ident.get("executor") == "codex":
        ident.setdefault("effort", "high" if judge else "medium")
    if ident.get("executor") != "claude":
        ident.pop("allowed_tools", None)
        ident.pop("permission_mode", None)
    elif confined is not None:
        ident.setdefault("permission_mode", "bypassPermissions" if confined else "acceptEdits")
    return ident


def _identity(arm: dict, fields=IDENTITY_FIELDS) -> dict:
    ident = {k: arm[k] for k in fields if arm.get(k) not in (None, "")}
    if isinstance(ident.get("base_url"), str):
        ident["base_url"] = ident["base_url"].rstrip("/")
    return ident


def _snapshot_instructions(plan: dict, out: Path):
    """Point each arm at a copy of its instructions in the run directory, named by the digest of the same bytes,
    so the recorded digest is what every run received even when the source changes during a trial."""
    for name, arm in plan["arms"].items():
        if not arm.get("instructions"):
            continue
        src = Path(arm["instructions"])
        try:
            data = src.read_bytes()
        except OSError as exc:
            raise TrialError(f"arm '{name}' instructions {src}: {exc.strerror}") from None
        sha = hashlib.sha256(data).hexdigest()
        target = out / "instructions" / (sha + src.suffix)
        if not target.exists():
            target.parent.mkdir(exist_ok=True)
            _write_atomic(target, data)
        arm.update(instructions=str(target), instructions_source=str(src), instructions_sha256=sha)


def _snapshot_artifacts(plan: dict, out: Path):
    """Point each artifact arm at a frozen copy under the run directory, named by its digest, so every job
    reads the same content even if the source changes during a trial - the artifact counterpart of
    _snapshot_instructions. The copy is always a directory (a single-file artifact's own file sits inside
    it under its original name), so run_artifact can copy it into a job's working directory uniformly."""
    for name, arm in plan["arms"].items():
        if arm.get("executor") != "artifact":
            continue
        src = Path(arm["artifact"])
        sha = arm["artifact_sha256"]
        target = out / "artifacts" / sha
        if not target.exists():
            target.parent.mkdir(exist_ok=True)
            tmp = out / "artifacts" / f".tmp-{sha}-{os.urandom(4).hex()}"
            if src.is_dir():
                shutil.copytree(src, tmp, symlinks=True)
            else:
                tmp.mkdir()
                shutil.copy2(src, tmp / src.name)
            os.replace(tmp, target)
        arm.update(artifact=str(target), artifact_source=str(src))


def _stored_plan(out: Path) -> dict:
    path = out / "plan.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise TrialError(f"cannot read {path}: {exc}") from None


STALE_LOCK_SECONDS = 6 * 3600  # fallback only, for a lock this process cannot identify (see _dead_lock_holder)


def _lock_owner() -> str:
    return f"{os.getpid()}@{socket.gethostname()}"


def _dead_lock_holder(path: Path) -> bool | None:
    """Whether the process named in a lock file is confirmed gone: True when its pid no longer exists on
    this host, False when it is still alive (or the lock is held by another user we cannot signal, which
    still proves it is alive), None when the lock predates this format or names a different host, so
    liveness cannot be checked here and the caller falls back to the lock's age."""
    try:
        owner = path.read_text().strip()
        pid_s, host = owner.split("@", 1)
        pid = int(pid_s)
    except (OSError, ValueError):
        return None
    if host != socket.gethostname():
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError:
        return None
    return False


@contextlib.contextmanager
def _lock(out: Path):
    """One run or recheck per run directory at a time: another would replace the first one's jobs and
    records. Where fcntl is available (every host main() actually runs on: native Windows is refused
    before this is ever called), an flock() on out/.trial.lock does it: the OS drops the lock the instant
    the holding process exits, however it exits, so no process ever has to guess whether another one is
    still alive, and two processes racing to reclaim what looks like a stale lock - the flaw in the older
    scheme below - cannot both succeed. Without fcntl (a direct caller on some other host), fall back to an
    O_EXCL lock file that records its own pid and host, so a lock whose process has confirmed exited is
    reclaimed immediately - never after 6 hours, and never while that process (however long it runs) is
    still alive - and a lock this process cannot identify (a different host, or an older lock format) falls
    back to reclaiming it only once it is implausibly old."""
    path = out / ".trial.lock"
    if fcntl is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise TrialError(f"{out} is in use by another trial.py run or recheck (lock: {path}); wait "
                                 "for it, or use a new --out") from None
            with contextlib.suppress(OSError):
                os.ftruncate(fd, 0)
                os.write(fd, _lock_owner().encode())
            yield
        finally:
            os.close(fd)  # releases the flock too, however this process ends
        return
    owner = _lock_owner()
    for attempt in (0, 1):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(owner)
            break
        except FileExistsError:
            dead = _dead_lock_holder(path)
            if dead is None:
                try:
                    dead = (dt.datetime.now().timestamp() - path.stat().st_mtime) > STALE_LOCK_SECONDS
                except OSError:
                    dead = False
            if attempt == 0 and dead:
                with contextlib.suppress(OSError):
                    os.unlink(path)
                continue
            raise TrialError(f"{out} is in use by another trial.py run or recheck (lock: {path}); wait for it, "
                             "remove the lock file yourself once you have confirmed that process is gone, or "
                             "use a new --out") from None
    try:
        yield
    finally:
        try:
            if path.read_text().strip() == owner:
                os.unlink(path)
        except OSError:
            pass


def _refuse_changes(what: str, entry: dict, runs: list[dict], field: str, stored_entry: dict | None, out: Path, hint: str,
                    fields=IDENTITY_FIELDS, new_confined=None):
    """Refuse `entry` when its settings differ from what `runs` recorded in `field` (plan.json for older runs).
    `new_confined(scenario_name) -> bool | None` (arms only; judges have no permission_mode field), when
    given, is the confinement THIS rerun would now apply for that scenario - so a claude arm's unset
    "permission_mode" compares against the default confinement actually implies now, never against a fixed
    guess or against merely repeating whatever each old run happened to record (either of which would let a
    real confined/unconfined change go undetected, or refuse a plain unchanged rerun - see _effective)."""
    if not runs:
        return
    records = [(r[field], fields, r.get("scenario")) for r in runs if field in r]
    if len(records) < len(runs):
        if not stored_entry:
            raise TrialError(f"{out} holds runs of {what} with no record of their settings; use a new --out")
        records.append((_identity(stored_entry, IDENTITY_FIELDS[:4]), IDENTITY_FIELDS[:4], None))
    judge = fields is JUDGE_FIELDS
    raw_now = _identity(entry, fields)
    unresolved = str(raw_now.get("model", "")).startswith("latest:")  # a dry run that asked no endpoint
    for record, rec_fields, scenario in records:
        confined = new_confined(scenario) if new_confined and scenario else None
        record = _effective(record, judge, confined)
        now = _effective(raw_now, judge, confined)
        diffs = []
        for k in rec_fields:
            if record.get(k) == now.get(k) or (k == "model" and unresolved):
                continue
            if k in ("instructions_sha256", "artifact_sha256", "resources_sha256", "command"):
                diffs.append("different " + k.split("_")[0])
            else:
                diffs.append(f"{k} {now.get(k, 'unset')} (was {record.get(k, 'unset')})")
        if diffs:
            raise TrialError(f"{what} now has {', '.join(diffs)}, but {out} holds runs made with the earlier settings; {hint}")


def _merge_stored_plan(out: Path, plan: dict) -> dict:
    """The plan to record in a run directory that may already hold runs. An arm or judge whose recorded settings
    differ from what the stored runs recorded is refused, so one directory never mixes models, instructions, or
    judges. Arms and scenarios left out by --arms and --only keep their stored entries, and every latest:
    resolution the directory has made stays recorded."""
    stored = _stored_plan(out)
    results = [r for _, r in _load_results(out)[0]]
    specs = {**{sp["name"]: _current(sp) for sp in stored.get("scenarios", [])}, **{sp["name"]: sp for sp in plan["scenarios"]}}
    # What confinement a claude arm would now resolve to for a given scenario name, from THIS rerun's own
    # plan (sandbox default, any --sandbox override, and the scenario's own "sandbox") - never from what an
    # old run happened to record - so _refuse_changes catches an actual confined/unconfined change and
    # nothing else (see _effective). None when the scenario is not known to this rerun at all.
    new_confined = lambda scenario: (not _unconfined(_effective_sandbox(plan, specs[scenario]))) if scenario in specs else None
    for name, arm in plan["arms"].items():
        _refuse_changes(f"arm '{name}'", arm, [r for r in results if r.get("arm") == name], "identity",
                        stored.get("arms", {}).get(name), out, "restore them or use a new --out",
                        new_confined=new_confined)
    # A scenario the directory's plan.json does not list may be judged; a verdict there counts.
    judged_scenario = lambda r: (specs.get(r.get("scenario")) or {"judge": "unknown"}).get("judge")
    judged = [r for r in results if r.get("status") == "ok" and r.get("judge") and judged_scenario(r)]
    unjudged = [r for r in results if r.get("status") == "ok" and not r.get("judge") and judged_scenario(r)
                and "check_error" not in (r.get("checks") or {})]
    rejudge = f"re-judge every stored run with `trial.py recheck {out} --judge JSON`, or use a new --out"
    if plan.get("judge"):
        if unjudged:
            raise TrialError(f"{out} holds runs scored without a judge; judge them with `trial.py recheck {out} --judge JSON` "
                             "first, or use a new --out")
        want = plan["judge"].get("model", plan["judge"]["executor"])
        for r in judged:  # re-judged by an earlier runtime, which recorded only the judge's model
            if "judge_identity" not in r and r["judge"].get("judge_model") not in (None, want):
                raise TrialError(f"the judge now has model {want}, but {out} holds verdicts from {r['judge']['judge_model']}; {rejudge}")
        _refuse_changes("the judge", plan["judge"], judged, "judge_identity", stored.get("judge"), out, rejudge, JUDGE_FIELDS)
    elif judged:
        raise TrialError(f"the plan has no judge, but {out} holds judge verdicts; restore the judge or use a new --out")
    merged = dict(plan)
    merged["resolved"] = _record_resolutions(stored.get("resolved"), [*stored.get("arms", {}).values(), stored.get("judge"),
                                                                      *plan["arms"].values(), plan.get("judge")])
    merged["arms"] = {**stored.get("arms", {}), **plan["arms"]}
    names = {sp["name"] for sp in plan["scenarios"]}
    merged["scenarios"] = plan["scenarios"] + [sp for sp in stored.get("scenarios", []) if sp["name"] not in names]
    return merged


def schedule(plan):
    """All (arm, scenario, repeat) jobs, interleaved: arm order is shuffled per block."""
    rng = random.Random(plan["seed"])
    jobs = []
    for r in range(1, plan["repeats"] + 1):
        for spec in plan["scenarios"]:
            order = list(plan["arms"])
            rng.shuffle(order)
            jobs += [(arm, spec, r) for arm in order]
    return jobs


# ---------------------------------------------------------------- executors

def _require_tomllib():
    """tomllib is 3.11+ stdlib, needed only to read an existing ~/.codex/config.toml (a custom model
    provider) - never for the common case of no config at all, which is why this is checked lazily rather
    than at import time (see the module-level try/except above). macOS's own /usr/bin/python3 is often
    older than this."""
    if tomllib is None:
        raise TrialError(f"reading {CODEX_HOME_SRC / 'config.toml'} needs Python 3.11 or newer for its "
                         f"built-in tomllib (this is running under {sys.version.split()[0]}); install a "
                         "newer Python (a Homebrew or python.org install on macOS is usually 3.11+) and run "
                         "this script with it")
    return tomllib


def _provider_config(model: str, effort: str) -> str:
    """Minimal Codex config: the user's model provider, nothing that loads instructions."""
    lines = [f'model = "{model}"', f'model_reasoning_effort = "{effort}"',
             'model_reasoning_summary = "detailed"', 'web_search = "disabled"',
             # no plugin catalog, apps, or memories: each would load outside the arm and cost disk per run
             "[features]", "plugins = false", "remote_plugin = false", "apps = false", "memories = false", ""]
    src = CODEX_HOME_SRC / "config.toml"
    if src.exists():
        cfg = _require_tomllib().loads(src.read_text())
        prov = cfg.get("model_provider")
        block = cfg.get("model_providers", {}).get(prov) if prov else None
        if block:
            lines.insert(4, f'model_provider = "{prov}"')
            lines.append(f"\n[model_providers.{prov}]")
            for k, v in block.items():
                lines.append(f"{k} = {json.dumps(v)}")
    return "\n".join(lines) + "\n"


def _key_prefix(env_file: Path | None, var: str | None, target: str | None = None) -> list[str]:
    """Export one variable from the provider credential file, as `target` (default: its own name), to the
    command that follows. A subshell sources the file, so nothing else in it is exported, and the value is
    never read here. Run it outside bubblewrap: the sandbox then inherits the variable, never the file."""
    env_file = Path(env_file).expanduser().resolve() if env_file else None
    if not (env_file and env_file.exists() and var):
        return []
    for name in (var, target or var):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise TrialError(f"invalid environment variable name {name!r} for the provider key")
    return ["sh", "-c", 'k=$(. "$0" >/dev/null 2>&1; eval "printf %s \\"\\${$1-}\\""); eval "export $2=\\"\\$k\\""; shift 2; exec "$@"',
            str(env_file), var, target or var]


def _open_record(path: Path):
    """Open a run record for appending. An agent can replace the record between turns; a link or special file
    it left there is removed, never followed or waited on."""
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(path, flags, 0o644)
        if stat.S_ISREG(os.fstat(fd).st_mode):
            return os.fdopen(fd, "ab")
        os.close(fd)
    except OSError as exc:
        if exc.errno not in (errno.ELOOP, errno.ENXIO, errno.EISDIR, errno.EACCES, errno.EPERM):
            raise
    _own(path.parent)
    _remove(path)
    return os.fdopen(os.open(path, flags | os.O_EXCL, 0o644), "ab")


def _run(cmd, *, cwd, env, stdin_text, timeout, stdout_path, stderr_path):
    with _open_record(stdout_path) as out, _open_record(stderr_path) as err:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=out,
                                stderr=err, start_new_session=True)
        try:
            proc.communicate(stdin_text.encode() if stdin_text is not None else None, timeout=timeout)
            return proc.returncode, False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            return None, True



# Well-known locations under /run a DNS stub resolver keeps its files in, read back in (read-only) after
# _hide_run's "--tmpfs /run" below so name resolution keeps working over the network confinement otherwise
# leaves reachable; a plain /etc/resolv.conf that is not a symlink into /run (no systemd-resolved, no
# resolvconf) needs none of these; each is included only when it exists on this host.
_RUN_RESOLVERS = (Path("/run/systemd/resolve"), Path("/run/resolvconf"))


def _hide_run() -> list[str]:
    """"--tmpfs /run" (plus a read-only rebind of whichever resolver keeps its files there): "/run" holds
    Unix-domain sockets with no network-namespace boundary of their own - a user systemd/D-Bus bus, a
    container runtime's control socket, an X11 or Wayland socket - that a read-only bind of "/" leaves
    fully reachable from inside confinement even with the network namespace shared, letting a confined
    process reach the host well beyond any model API it was meant to call."""
    cmd = ["--tmpfs", "/run"]
    for d in _RUN_RESOLVERS:
        if d.is_dir():
            cmd += ["--ro-bind", str(d), str(d)]
    return cmd


def confine_prefix(job_dir: Path, readable: list[Path], *, network=True, writable=True, chdir: Path | None = None,
                   out: Path | None = None, protect: list[Path] = ()) -> list[str]:
    """Wrap a command in bubblewrap: the host is read-only, the user's home is hidden, "/run" is hidden
    (see _hide_run), the command and everything it starts live in their own process namespace and end with
    it, and only the run directory is writable. Network stays available for model APIs unless network is
    False. `out` (the run directory an --out outside it was given), when it sits outside both the home and
    "/tmp" tmpfs mounts already below, is hidden the same way: otherwise a confined process can list its
    sibling run directories and read plan.json two directories up from its own job directory, since nothing
    else in that case hides `out`'s parent, which the read-only "/" bind still exposes whole. `protect`
    names paths inside `job_dir` (an arm's "resources" - see _copy_readonly) that stay read-only to the
    confined process even though the job directory around them is writable: bound again, read-only, AFTER
    the writable job_dir bind below (bwrap applies binds in order, so a later one wins for any path it
    covers), since merely clearing a file's own write bit is not enough - the agent still owns the writable
    directory it sits in and can chmod it back before writing."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise TrialError("confined runs need bubblewrap (bwrap); install it, or pass --sandbox none "
                         "(or plan/scenario \"sandbox\": \"none\") to run unconfined")
    home = Path.home()
    cmd = [bwrap, "--ro-bind", "/", "/", "--tmpfs", str(home), "--dev", "/dev", "--proc", "/proc",
           "--tmpfs", "/tmp"] + _hide_run() + ["--unshare-pid", "--die-with-parent"] + ([] if network else ["--unshare-net"])
    if out is not None and out.exists() and not (out.is_relative_to(home) or out.is_relative_to(Path("/tmp"))):
        cmd += ["--tmpfs", str(out)]
    for path in readable:
        if path.is_symlink():
            # Recreate the link itself: binding it would put a copy of its target at the link's path, and a
            # launcher that resolves its package from its own location (npm's bin/ links) then looks in the
            # wrong directory. The target is exposed separately (_executor_readable adds the resolved path).
            cmd += ["--symlink", os.readlink(path), str(path)]
        elif path.exists():
            cmd += ["--ro-bind", str(path), str(path)]
    cmd += ["--bind" if writable else "--ro-bind", str(job_dir), str(job_dir)]
    for path in protect:
        if path.exists():
            cmd += ["--ro-bind", str(path), str(path)]
    return cmd + ["--chdir", str(chdir or job_dir / "work"), "--"]


def _codex_sandbox(spec):
    """'confined' (default) runs Codex unsandboxed inside bubblewrap so agents can commit; 'none' runs it the
    same way but without bubblewrap (the explicit, documented opt-out - Codex itself rejects "-s none", so
    it is mapped to its own fully-open mode instead); any other value is Codex's own sandbox mode name,
    passed straight through, to use instead of this runtime's bubblewrap confinement for the agent process
    itself (checks, git, and judges still confine unless the scenario's "sandbox" is literally "none")."""
    mode = spec.get("sandbox", "confined")
    if mode in ("confined", "none"):
        return "danger-full-access", mode == "confined"
    return mode, False


def _unconfined(spec: dict) -> bool:
    """Whether this runtime's own host-level bubblewrap protection - for checks, git, and judges, none of
    which are Codex or Claude processes with a sandbox vocabulary of their own - is off for this scenario.
    True only for the literal, documented opt-out "sandbox": "none"; any other value (a typo, or a Codex-
    native mode such as "workspace-write" that only changes what run_codex passes to Codex's own -s flag)
    still gets bubblewrap here, so a value meant only for Codex's inner sandbox can never silently drop the
    outer one that checks, git, and judges rely on."""
    return spec.get("sandbox", "confined") == "none"


def _resolve_binary(name: str, arm: dict, env_var: str) -> str:
    """An executor binary: the arm's "binary", then `env_var` (TRIAL_CODEX_BIN / TRIAL_CLAUDE_BIN), then
    the parent process's own PATH. No install-path guesses (no /opt/claude-code, no ~/.npm-global): those
    were this one host's layout, not every host's. A "binary" or env_var value is resolved the way a
    shell would resolve it - ~ expanded, then a bare name (or one that still does not exist after
    expansion) looked up on PATH - rather than treated as a literal path relative to the current
    directory, which bwrap would otherwise fail on with an opaque "Can't mkdir parents"."""
    found = arm.get("binary") or os.environ.get(env_var) or shutil.which(name)
    if not found:
        raise TrialError(f"cannot find {name} on PATH; set the arm's \"binary\", or {env_var}")
    expanded = Path(found).expanduser()
    if expanded.exists():
        return str(expanded)
    which = shutil.which(found)
    if which:
        return which
    raise TrialError(f"cannot find {name} binary {found!r} (from the arm's \"binary\" or {env_var}): it is "
                     "not a path that exists and no such name is on PATH")


def _read_shebang(path: Path) -> list[str]:
    """A script's interpreter line, split into words, or [] when `path` is not a text script (a compiled
    binary, or unreadable)."""
    try:
        with path.open("rb") as f:
            head = f.read(4096)
    except OSError:
        return []
    if not head.startswith(b"#!"):
        return []
    try:
        return shlex.split(head.split(b"\n", 1)[0][2:].decode())
    except (UnicodeDecodeError, ValueError):
        return []


def _executor_readable(binary: str) -> list[Path]:
    """Read-only paths a confined executor needs, derived from the resolved binary itself rather than an
    assumed directory depth: its own directory before and after following symlinks (an npm/pnpm/volta shim
    points outside the shim's own directory), the package root above it when it sits in a bin/ or .bin/
    directory (with a sibling lib/ for an npm global install), and the interpreter a script's shebang names
    (for example the node runtime a JS launcher needs). Each is included only if it exists.

    The sandbox hides the user's home directory entirely (see confine_prefix); a package root (below) is
    punched back through only when it sits well below home, never when it IS home or one of its immediate
    children (~/.local, ~/.cargo, ~/bin, ...) - those are broad, multi-purpose directories that can hold
    unrelated credentials, not scoped to this one executor's own package. A real install nests further
    below (for example ~/.npm-global/lib/node_modules/<pkg>).

    The binary's own directory (before or after following symlinks, or the interpreter's) is narrower still
    where it needs to be: it is exposed whole when it is scoped to this one executor - including an
    immediate child of home such as ~/bin, where the binary is commonly the only thing there - but never
    when it is home itself, or a directory exactly one level below one of those immediate children (a shim
    placed directly in ~/.local/bin or ~/.cargo/bin, for example): package managers and version managers
    fill those with many unrelated entries, which a real native app-installer layout can also expose
    (~/.local/bin/claude symlinked to a versioned install elsewhere, sitting beside unrelated user scripts).
    Where the binary's own directory is this broad, only the binary FILE itself is exposed (bwrap can
    --ro-bind a single file exactly like a directory), never the whole directory around it."""
    home = Path.home().resolve()

    def too_broad(d: Path) -> bool:
        """Used for a package root discovered above the binary (below): home itself, or one of its
        immediate children, which is as far as a root belonging to one specific package should ever need
        to reach up."""
        return d == home or d.parent == home

    def narrow_to_file(d: Path) -> bool:
        """Used for the binary's own directory: home itself (mishandled otherwise - see the "blocked" set
        below), or a directory exactly one level below one of home's immediate children. An immediate
        child of home itself (~/bin, ~/.local, ~/.cargo, ...) is deliberately NOT included here: unlike a
        package root reached from well below, this is the binary's own containing directory, and for a
        shallow single-tool install directly under home that directory holds little else."""
        return d == home or d.parent.parent == home

    def dir_or_file(path: Path) -> Path:
        d = path.parent
        return path if narrow_to_file(d) else d

    original = Path(binary).expanduser()
    resolved = original.resolve()
    dirs = {dir_or_file(original), dir_or_file(resolved)}
    for ancestor in resolved.parents:
        if ancestor.name in ("bin", ".bin"):
            root = ancestor.parent
            if not too_broad(root):
                dirs.add(root)
                lib = root / "lib"
                if lib.is_dir():
                    dirs.add(lib)
            break
    words = _read_shebang(resolved)
    if words:
        interp = words[1] if words[0].endswith("env") and len(words) > 1 else words[0]
        found = interp if Path(interp).is_absolute() else shutil.which(interp)
        if found:
            dirs.add(dir_or_file(Path(found).resolve()))
    # Never punch through "/" itself (which would re-mount the whole host over the tmpfs bwrap already put
    # at the user's home) or home or any of its ancestors (which would remount over that same tmpfs) - a
    # binary living directly under "/", or under a real top-level "/bin" on a distro without a merged
    # /usr, would otherwise re-expose the host home confine_prefix means to hide.
    blocked = {Path("/"), home, *home.parents}
    return sorted({d for d in dirs if d.exists() and d not in blocked}, key=str)


def _extend_path(path: str, dirs: list[Path]) -> str:
    """`path` with `dirs` (the ones that exist, and are not already on it) inserted right after its first
    entry - the scenario's own fake-tools directory, which isolated_env always puts first, whether or not
    the scenario supplies any tools of its own - so a scenario's fake gh/curl/make is still found before a
    confined executor's own directories or interpreter, which in turn are found before the system PATH."""
    existing = path.split(os.pathsep) if path else []
    additions = [str(d) for d in dict.fromkeys(dirs) if d.exists() and str(d) not in existing]
    if not additions:
        return path
    head, tail = (existing[:1], existing[1:]) if existing else ([], [])
    return os.pathsep.join(head + additions + tail)


def _protected_resources(arm: dict, env: dict) -> list[Path]:
    """Where an arm's "resources" (see _with_resources, isolated_env) actually land inside a confined run's
    writable job directory: paths confine_prefix's own "protect" re-binds read-only after the job directory
    itself, so the agent cannot chmod its way back to writable (merely clearing a copy's own write bit -
    see _copy_readonly - is not enough on its own, since the agent still owns the writable directory
    around it)."""
    return [Path(env["HOME"]) / rel for rel in (arm or {}).get("resources", {})]


def _resolve_key(arm: dict, var: str, target: str, where: str) -> tuple[list[str], dict]:
    """How the one key variable an arm uses reaches its run: a subshell prefix that exports it from an
    env_file (the arm's own, or TRIAL_ENV_FILE) without exposing the rest of that file, or, with neither
    set, its value copied straight from this process's own environment. Raises when nothing supplies it,
    naming all three ways to."""
    env_file = _env_file_for(arm)
    if env_file:
        if not env_file.exists():
            raise TrialError(f"{where}: env_file {env_file} does not exist")
        return _key_prefix(env_file, var, target), {}
    value = os.environ.get(var)
    if not value:
        raise TrialError(f"{where}: no value for {var}; supply it with the arm's \"env_file\", with "
                         "TRIAL_ENV_FILE, or by setting it in this process's own environment")
    return [], {target: value}


# The one login file each agent CLI keeps for a non-API-key sign-in (a ChatGPT login for Codex, a
# Claude.ai OAuth login for Claude), copied into a run's private home only when the arm explicitly opts in
# with "copy_auth": true (see trials.md) - never by default, since the agent under test can then read it.
_AUTH_FILE = {"codex": (CODEX_HOME_SRC / "auth.json", Path("auth.json")),
             "claude": (Path.home() / ".claude" / ".credentials.json", Path(".claude") / ".credentials.json")}


def _copy_auth(executor: str, arm: dict, dest_home: Path, where: str) -> None:
    """With the arm's explicit "copy_auth": true, copy this host's own login file for `executor` into the
    run's private home, for a login with no API key to put behind env_file. Never copied otherwise."""
    if not arm.get("copy_auth"):
        return
    src, rel = _AUTH_FILE[executor]
    if not src.exists():
        raise TrialError(f"{where} sets \"copy_auth\": true, but {src} does not exist")
    dest = dest_home / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dest)


def _preflight_binaries(plan: dict) -> None:
    """Before scheduling any jobs, confirm every agent binary this run would find only by searching PATH -
    no explicit arm "binary" and no TRIAL_CODEX_BIN/TRIAL_CLAUDE_BIN, so this host's own PATH decided it -
    actually runs `--version` inside the same confinement a job would use. A broken PATH shim (a launcher
    that re-execs and cannot find the real CLI once confinement hides the paths it assumed) would otherwise
    surface only per job, after plan.json is written and each job's own setup.sh has already run. An arm
    or judge that names its own "binary" (or the TRIAL_*_BIN variable) is trusted as given, exactly as
    every other explicit executor setting is, and is never preflighted."""
    if plan.get("sandbox", "confined") == "none" or not shutil.which("bwrap"):
        return  # nothing this check would add: unconfined already behaves like the parent shell's own PATH,
                # and without bubblewrap the first real job already explains that plainly
    seen = set()
    entries = [(f"arm '{name}'", arm) for name, arm in plan["arms"].items() if arm.get("executor") in ("codex", "claude")]
    if plan.get("judge"):
        entries.append(("judge", plan["judge"]))
    for where, arm in entries:
        executor = arm["executor"]
        env_var = "TRIAL_CODEX_BIN" if executor == "codex" else "TRIAL_CLAUDE_BIN"
        if arm.get("binary") or os.environ.get(env_var):
            continue
        binary = _resolve_binary(executor, arm, env_var)
        readable = _executor_readable(binary) + [Path(p).expanduser() for p in arm.get("readable", [])]
        key = (binary, tuple(str(p) for p in readable))
        if key in seen:
            continue
        seen.add(key)
        with tempfile.TemporaryDirectory(prefix="trial-preflight-") as tmp:
            job_dir = Path(tmp)
            (job_dir / "work").mkdir()
            prefix = confine_prefix(job_dir, readable)
            env = {"PATH": _extend_path(os.pathsep.join(SYSTEM_PATH), readable), "HOME": str(job_dir)}
            hint = (f"set the arm's \"binary\" or {env_var} to the real executable (a version-manager shim's "
                   f"own launcher can re-exec a real CLI it finds by re-reading $HOME, which confinement "
                   f"replaces - name the resolved path directly, e.g. `volta which {executor}`, "
                   f"`mise which {executor}`, or `asdf which {executor}`), or add \"readable\" paths it needs")
            try:
                r = subprocess.run(prefix + [binary, "--version"], cwd=job_dir / "work", env=env,
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
            except OSError as exc:
                raise TrialError(f"{where}'s {executor} binary {binary} (found on PATH) could not be run "
                                 f"confined: {exc.strerror or exc}; {hint}") from None
            except subprocess.TimeoutExpired:
                raise TrialError(f"{where}'s {executor} binary {binary} (found on PATH) did not answer "
                                 f"--version confined within 30s; {hint}") from None
            if r.returncode != 0:
                lines = (r.stderr or r.stdout).strip().splitlines()
                detail = lines[-1] if lines else "no output"
                raise TrialError(f"{where}'s {executor} binary {binary} (found on PATH) failed --version "
                                 f"confined ({detail}); {hint}")


def run_codex(arm, spec, job_dir: Path, env):
    home = job_dir / "home"
    home.mkdir()
    (home / "config.toml").write_text(_provider_config(arm["model"], arm.get("effort", "medium")))
    cache = CODEX_HOME_SRC / "models_cache.json"
    if cache.exists():
        shutil.copy(cache, home / "models_cache.json")
    if arm.get("instructions"):
        shutil.copy(arm["instructions"], home / "AGENTS.md")
    _copy_auth("codex", arm, home, "arm using codex")
    try:
        env = dict(env, CODEX_HOME=str(home))
        if arm.get("copy_auth"):
            # The copied ChatGPT login (above) is this arm's whole authentication; a key is neither needed
            # nor requested, so a user with no API key at all can still run (see trials.md, "Logging in
            # without an API key").
            key_prefix, key_env = [], {}
        else:
            var = arm.get("api_key_var") or _default_key_var("codex")
            key_prefix, key_env = _resolve_key(arm, var, var, "arm using codex")
        env = dict(env, **key_env)
        codex = _resolve_binary("codex", arm, "TRIAL_CODEX_BIN")
        sandbox, confined = _codex_sandbox(spec)
        readable = _executor_readable(codex) + [Path(p).expanduser() for p in arm.get("readable", [])]
        env["PATH"] = _extend_path(env.get("PATH", ""), readable)
        # the key is exported outside, then bwrap inherits it; the credential file itself stays hidden
        prefix = key_prefix + (confine_prefix(job_dir, readable, out=job_dir.parent.parent,
                                              protect=_protected_resources(arm, env)) if confined else [])
        common = ["--skip-git-repo-check", "-s", sandbox,
                  "-m", arm["model"], "-c", f"model_reasoning_effort={arm.get('effort', 'medium')}",
                  "--add-dir", str(job_dir / "harness"), "--json"]
        timeout = spec.get("timeout_s", 900)
        status = "ok"
        thread = None
        for i, prompt in enumerate([spec["prompt"], *spec.get("followups", [])]):
            final = job_dir / f"final-{i}.md"
            if i == 0:
                cmd = [codex, "exec", *common, "-C", str(job_dir / "work"), "-o", str(final), "-"]
            else:
                if not thread:
                    status = "no-thread-for-followup"
                    break
                cmd = [codex, "exec", *common, "-o", str(final), "resume", thread, "-"]
            code, timed_out = _run(prefix + cmd, cwd=job_dir / "work", env=env, stdin_text=prompt,
                                   timeout=timeout, stdout_path=job_dir / "events.jsonl",
                                   stderr_path=job_dir / "stderr.log")
            _own(job_dir)
            thread = thread or _thread_id(job_dir / "events.jsonl")
            if timed_out:
                status = "timeout"
                break
            if code != 0:
                status = f"exit-{code}"
                break
        return status, confined
    finally:
        # Normal completion is pruned by _run_job_once's own _prune(job_dir) call; this covers every path
        # that raises before reaching it (a missing key, a missing binary, missing bubblewrap, ...), so a
        # copied login never survives a run that never got that far (see trials.md, "Reading results").
        with contextlib.suppress(OSError):
            _remove(home / "auth.json")


def _provider_block() -> dict:
    """The Codex config's model provider settings (base_url, env_key, ...), or {}."""
    src = CODEX_HOME_SRC / "config.toml"
    if not src.exists():
        return {}
    cfg = _require_tomllib().loads(src.read_text())
    return cfg.get("model_providers", {}).get(cfg.get("model_provider") or "", {})


def _provider_key_var():
    """Name of the environment variable holding the Codex model provider's key (read from config, never its value)."""
    return _provider_block().get("env_key")


def _claude_proxy(arm, env):
    """The key Claude Code authenticates with (api_key_var, default ANTHROPIC_API_KEY, from the arm's
    env_file, TRIAL_ENV_FILE, or this process's own environment) always reaches the child, renamed to
    ANTHROPIC_API_KEY; with "base_url" set, that endpoint is used too. Without base_url, Claude uses its
    own default endpoint."""
    var = arm.get("api_key_var") or "ANTHROPIC_API_KEY"
    prefix, key_env = _resolve_key(arm, var, "ANTHROPIC_API_KEY", "claude arm")
    env = dict(env, **key_env)
    if arm.get("base_url"):
        env = dict(env, ANTHROPIC_BASE_URL=arm["base_url"])
    return env, prefix


def run_claude(arm, spec, job_dir: Path, env):
    """Claude Code in bare mode: no hooks, plugins, memory, or CLAUDE.md discovery.

    With "base_url" (an Anthropic-compatible endpoint such as a model proxy) Claude talks to that
    endpoint instead of its own default one; either way the run is confined like codex runs, with HOME
    its own. Confined by anything other than the literal "none" - a typo or a Codex-native sandbox mode
    name (which has no meaning for a claude arm) fails safe to confined, exactly like checks, git, and
    judges (see _unconfined); only "none" ever turns this runtime's own bubblewrap off."""
    binary = _resolve_binary("claude", arm, "TRIAL_CLAUDE_BIN")
    confined = not _unconfined(spec)
    # The effective default is recorded back onto the arm so it lands in the run's identity: a rerun that
    # would silently compare a confined and an unconfined Claude arm under different default permission
    # modes is refused, the same way any other identity change is (see trials.md).
    permission_mode = arm.setdefault("permission_mode", "bypassPermissions" if confined else "acceptEdits")
    cmd = [binary, "-p", "--bare", "--output-format", "stream-json", "--verbose", "--model", arm["model"],
           "--permission-mode", permission_mode, "--add-dir", str(job_dir / "harness")]
    if arm.get("effort"):
        cmd += ["--effort", arm["effort"]]
    if arm.get("instructions"):
        cmd += ["--append-system-prompt-file", arm["instructions"]]
    if arm.get("allowed_tools"):
        cmd += ["--allowed-tools", *arm["allowed_tools"]]
    env, prefix = _claude_proxy(arm, env)
    _copy_auth("claude", arm, Path(env["HOME"]), "arm using claude")
    try:
        readable = (_executor_readable(binary) + [Path(p).expanduser() for p in arm.get("readable", [])]
                    + ([Path(arm["instructions"])] if arm.get("instructions") else []))
        env["PATH"] = _extend_path(env.get("PATH", ""), readable)
        if confined:
            prefix = prefix + confine_prefix(job_dir, readable, out=job_dir.parent.parent,
                                             protect=_protected_resources(arm, env))  # the key is loaded outside, then bwrap inherits it
        timeout = spec.get("timeout_s", 900)
        for i, prompt in enumerate([spec["prompt"], *spec.get("followups", [])]):
            c = prefix + cmd + (["--continue"] if i else [])
            before = len(_read(job_dir / "events.jsonl", follow=False).splitlines())
            code, timed_out = _run(c, cwd=job_dir / "work", env=env, stdin_text=prompt, timeout=timeout,
                                   stdout_path=job_dir / "events.jsonl", stderr_path=job_dir / "stderr.log")
            _own(job_dir)
            for line in _read(job_dir / "events.jsonl", follow=False).splitlines()[before:]:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and event.get("type") == "result" and isinstance(event.get("result"), str):
                    _write_atomic(job_dir / f"final-{i}.md", event["result"].encode())
            if timed_out:
                return "timeout", confined
            if code != 0:
                return f"exit-{code}", confined
        return "ok", confined
    finally:
        # See run_codex's matching finally: normal completion is pruned by _run_job_once's own _prune(),
        # this covers every path that raises first (a missing key, a missing binary, missing bubblewrap, ...).
        with contextlib.suppress(OSError):
            _remove(Path(env["HOME"]) / ".claude" / ".credentials.json")


def run_command(arm, spec, job_dir: Path, env):
    prompt = spec["prompt"]
    prefix = []
    instructions = arm.get("instructions") or ""
    tool_dirs = [Path(p).expanduser() for p in arm.get("readable", [])]
    readable = [Path(spec["dir"]), *([Path(instructions)] if instructions else []), *tool_dirs]
    # Confined by anything other than the literal "none" (see _unconfined): a typo or a Codex-native
    # sandbox mode name, which means nothing to a plain shell command, must never silently drop it either.
    confined = not _unconfined(spec) and arm.get("confine", True)
    if confined:
        prefix = confine_prefix(job_dir, readable, out=job_dir.parent.parent,
                                protect=_protected_resources(arm, env))  # raises if bubblewrap is missing; never a silent fallback
    env = dict(env, PATH=_extend_path(env.get("PATH", ""), tool_dirs))
    code, timed_out = _run(prefix + ["sh", "-c", arm["command"]], cwd=job_dir / "work",
                           env=dict(env, TRIAL_PROMPT=prompt, TRIAL_SCENARIO_DIR=spec["dir"],
                                    TRIAL_JOB_DIR=str(job_dir), TRIAL_INSTRUCTIONS=instructions), stdin_text=prompt,
                           timeout=spec.get("timeout_s", 300), stdout_path=job_dir / "events.jsonl",
                           stderr_path=job_dir / "stderr.log")
    return ("timeout" if timed_out else ("ok" if code == 0 else f"exit-{code}")), confined


def run_artifact(arm, spec, job_dir: Path, env):
    """No model call: the frozen copy _snapshot_artifacts prepared becomes the working directory's content.
    A single produced file becomes the judged output directly (final-0.md, read the same way an executor's
    own final message is); more than one file leaves a bounded listing there instead, and a scenario naming
    its own "artifact" path picks a specific file precisely (see Run.__init__). "Produced" is counted from
    the artifact snapshot itself, never from the merged working directory: a scenario fixture may already
    have copied its own files into work/ before this executor runs, and those must never be mistaken for
    part of the artifact or turn a single-file artifact into an unreadable listing."""
    src = Path(arm["artifact"])
    shutil.copytree(src, job_dir / "work", dirs_exist_ok=True, symlinks=True)
    produced = sorted(p for p in src.rglob("*") if p.is_file() and not p.is_symlink())
    if len(produced) == 1:
        rel = produced[0].relative_to(src)
        shutil.copy2(job_dir / "work" / rel, job_dir / "final-0.md")
    elif produced:
        listing = "\n".join(str(p.relative_to(src)) for p in produced[:500])
        (job_dir / "final-0.md").write_text(listing)
    return "ok", True  # no process is run, so nothing of this runtime's own confinement applies


EXECUTORS = {"codex": run_codex, "claude": run_claude, "command": run_command, "artifact": run_artifact}


def _thread_id(events: Path):
    if events.exists():
        for line in _read(events, follow=False).splitlines():
            if '"thread.started"' in line:
                try:
                    return json.loads(line)["thread_id"]
                except (json.JSONDecodeError, KeyError):
                    pass
    return None


# ---------------------------------------------------------------- run record

COPY_LIMIT = 256 * 1024 ** 2  # copies for checks leave out larger files, which a sparse file makes cheap to plant


def _skip_for_copy(directory, names):
    skip = set(shutil.ignore_patterns(".git", "__pycache__")(directory, names))
    for name in names:
        try:
            mode = os.lstat(os.path.join(directory, name)).st_mode
        except OSError:
            skip.add(name)
            continue
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
            skip.add(name)
        elif stat.S_ISREG(mode) and os.lstat(os.path.join(directory, name)).st_size > COPY_LIMIT:
            skip.add(name)
    return skip


GIT_HARDENING = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
                 "-c", "core.pager=cat", "-c", "protocol.allow=never", "-c", "core.sshCommand=false",
                 "-c", "credential.helper=", "-c", "gpg.program=false", "-c", "core.alternateRefsCommand=false"]
# diff-producing subcommands get --no-ext-diff/--no-textconv (below) instead of a "-c diff.external=" config
# override: on current git that empty value is itself run as the external diff command, which fails with
# "external diff died" on any real diff - silently starving a check of the very diff it asked for. The two
# flags disable external diff drivers and textconv filters for that one invocation, the documented way,
# without needing a value at all.
DIFF_SUBCOMMANDS = {"diff", "log", "show"}
GIT_ENV = {"PATH": os.pathsep.join(SYSTEM_PATH), "HOME": "/tmp", "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
COMMAND_TAIL = 4000  # a command arm's raw stdout, bounded, when it wrote neither a final-*.md nor a parsed message


class Run:
    """What a check sees: the resulting state and the native record of one run."""

    def __init__(self, job_dir: Path, status: str, unconfined: bool = False, artifact: str | None = None):
        self.dir = job_dir
        self.workdir = job_dir / "work"
        self.harness = job_dir / "harness"
        self.status = status
        self.unconfined = unconfined  # "sandbox": "none" was resolved for this run; checks confine the same way
        raw_events = self.read(job_dir / "events.jsonl")
        self.events = []
        for line in raw_events.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):  # a command arm may print JSON scalars or lists
                self.events.append(event)
        self.messages = [t for t in (_message_text(e) for e in self.events) if t]
        finals = sorted(job_dir.glob("final-*.md"))
        art_path = (self.workdir / artifact) if artifact else None
        self.artifact_missing = False
        if art_path is not None and art_path.is_file() and not art_path.is_symlink():
            # a scenario's own "artifact" names the produced file that is the judged output, ahead of any
            # transcript-derived message - the same file for every executor that was asked to write one
            self.final_message = self.read(art_path)
        elif art_path is not None:
            # the scenario named an artifact the executor was asked to write, and it is not there: an
            # explicit marker, never a silent fall-back to the transcript, which is the failure the
            # artifact feature exists to catch (the judge would otherwise score what the agent *said* it
            # produced instead of what it actually produced).
            self.artifact_missing = True
            self.final_message = f"[artifact not produced: {artifact!r} was not found in the working directory]"
        elif finals:
            self.final_message = self.read(finals[-1])
        elif self.messages:
            self.final_message = self.messages[-1]
        else:  # a command arm that wrote no final-*.md: its own bounded, raw stdout tail
            self.final_message = raw_events[-COMMAND_TAIL:]
        self.commands = [c for c in (_command_text(e) for e in self.events) if c]
        self.calls = []
        for line in self.read(self.harness / "calls.jsonl").splitlines():
            try:
                self.calls.append(json.loads(line))
            except json.JSONDecodeError:
                self.calls.append({"raw": line})
        self.usage = _usage(self.events)

    def read(self, p: Path) -> str:
        """Read a file only if it resolves inside the run directory: an agent can plant links to host files."""
        try:
            if not p.resolve().is_relative_to(self.dir.resolve()):
                return ""
        except (OSError, RuntimeError):
            return ""
        return _read(p)

    def _git(self, args, cwd):
        """Git on the agent's repository, whose configuration the agent controls: known command-running
        settings are overridden, and git runs confined (read-only, no network) unless this run resolved to
        "sandbox": "none" - never a silent unconfined fallback when confinement was actually needed. A
        diff-producing subcommand (diff/log/show) additionally gets --no-ext-diff/--no-textconv, so an
        agent-configured external diff driver or textconv filter never runs (see DIFF_SUBCOMMANDS)."""
        diff_flags = ["--no-ext-diff", "--no-textconv"] if args and args[0] in DIFF_SUBCOMMANDS else []
        cmd = ["git", *GIT_HARDENING, *args[:1], *diff_flags, *args[1:]]
        cwd = Path(cwd or self.workdir)
        if not self.unconfined and cwd.exists():
            cmd = confine_prefix(self.dir, [], network=False, writable=False, chdir=cwd,
                                 out=self.dir.parent.parent) + cmd
        try:
            return subprocess.run(cmd, cwd=cwd if cwd.exists() else self.dir, env=GIT_ENV, capture_output=True,
                                  text=True, timeout=120)
        except (subprocess.TimeoutExpired, OSError):
            return None

    def git(self, *args, cwd=None) -> str:
        r = self._git(args, cwd)
        return r.stdout.strip() if r is not None and r.returncode == 0 else ""

    def git_rc(self, *args, cwd=None) -> int | None:
        r = self._git(args, cwd)
        return None if r is None else r.returncode

    def file(self, rel: str) -> str:
        return self.read(self.workdir / rel)

    def copy_workdir(self) -> Path:
        """A fresh copy of the working directory under the run directory, links kept as links, and .git,
        caches, and special files (FIFOs, sockets, devices) left out, for checks that run or change agent
        code; the caller removes its parent."""
        dst = Path(tempfile.mkdtemp(prefix="check-", dir=self.dir)) / "w"
        if self.workdir.is_symlink() or not self.workdir.is_dir():  # the agent replaced it: nothing of its own to copy
            dst.mkdir()
            return dst
        shutil.copytree(self.workdir, dst, symlinks=True, ignore=_skip_for_copy)
        return dst

    def sandboxed(self, cmd, cwd=None, timeout=120, env=None):
        """Run a command that executes agent-written code: no network, the host read-only, the user's home
        hidden, its own process namespace, and only `cwd` writable - unless this run resolved to "sandbox":
        "none", in which case it runs the same way but without bubblewrap. Returns the completed process,
        or None when it timed out."""
        cwd = Path(cwd or self.workdir)
        if self.unconfined:
            prefix = []
        else:
            prefix = confine_prefix(cwd, [], network=False, chdir=cwd, out=self.dir.parent.parent)
        base = {"PATH": os.pathsep.join(SYSTEM_PATH), "HOME": str(cwd), "TMPDIR": str(cwd), "LANG": "C.UTF-8",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            return subprocess.run(prefix + list(cmd), cwd=cwd, env=dict(base, **(env or {})),
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None


def _write_json(path: Path, obj):
    _write_atomic(path, json.dumps(obj, indent=1).encode())


def _dumps_finite(payload: dict, where: str) -> str:
    """`summarize --json` and `report` are read by other tools, some of which (a strict JSON parser such as
    Node's) reject a bare NaN or Infinity - the default json.dumps would otherwise silently emit one, most
    likely from a check.py that returned a non-finite measure as one of its own numeric check values (usage
    numbers are already sanitized before they reach either document - see _sane_numeric)."""
    try:
        return json.dumps(payload, indent=1, allow_nan=False)
    except ValueError as exc:
        raise TrialError(f"{where} would not be valid JSON ({exc}); a check.py likely returned a "
                         "non-finite number (NaN or Infinity) as a check value") from None


def _write_atomic(path: Path, data: bytes):
    """Write through a private temporary file, so a reader never sees a partial file; a link or directory an
    agent left in the file's place is replaced, never followed."""
    _own(path.parent)
    with contextlib.suppress(FileNotFoundError):
        if stat.S_ISDIR(os.lstat(path).st_mode):
            _remove(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _load_results(out: Path):
    """Finished results; unreadable ones (interrupted writes) are skipped and counted."""
    results, skipped = [], 0
    for p in sorted((out / "runs").glob("*/result.json")):
        if p.parent.name.startswith(".") or (p.parent.parent / f"{p.parent.name}.pending").exists():
            continue  # a discarded tree, or an attempt the runner never finished
        try:
            r = json.loads(_read(p, follow=False))
        except json.JSONDecodeError:
            r = None
        if isinstance(r, dict):
            results.append((p, r))
        else:
            skipped += 1
    return results, skipped


READ_LIMIT = 64 * 1024 ** 2  # an agent can leave a file of any apparent size, sparse or not


def _read(p: Path, follow: bool = True) -> str:
    """A regular file's text, or "": a FIFO or device an agent planted would block or never end, and with
    follow False a link it planted in place of a record is not followed."""
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK | (0 if follow else os.O_NOFOLLOW))
    except OSError:
        return ""
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):  # a directory, FIFO, or device
            return ""
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(READ_LIMIT)
    except OSError:
        return ""
    finally:
        os.close(fd)
    return data.decode(errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _content(e) -> list:
    """The content blocks of a claude stream-json assistant event, or [] for any other shape."""
    msg = e.get("message") if e.get("type") == "assistant" else None
    content = msg.get("content") if isinstance(msg, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _message_text(e):
    item = e.get("item")
    if e.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
        return str(item.get("text", ""))
    if e.get("type") == "assistant":  # claude stream-json
        return "".join(str(b.get("text", "")) for b in _content(e) if b.get("type") == "text")
    return None


def _command_text(e):
    item = e.get("item")
    if e.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "command_execution":
        return str(item.get("command", ""))
    for b in _content(e):
        if b.get("type") == "tool_use" and b.get("name") == "Bash":
            return str(b["input"].get("command", "")) if isinstance(b.get("input"), dict) else ""
    return None


def _flatten_numeric(obj, prefix="") -> dict:
    """Every numeric leaf under a usage object, keyed by its dotted path (a nested object such as Claude's
    "cache_creation" contributes "cache_creation.ephemeral_5m_input_tokens", not just its own top level)."""
    out = {}
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out[key] = v
        elif isinstance(v, dict):
            out.update(_flatten_numeric(v, key))
    return out


def _sane_numeric(obj) -> dict:
    """_flatten_numeric's result with every non-finite or negative leaf dropped. events.jsonl is writable
    inside the run's own sandbox for the runner's record-keeping, so an agent (or a command arm) under test
    can append its own lines to it; a stray NaN or a negative token count must never reach an aggregate, or
    a report written with json.dump(..., allow_nan=False) (see `report`) would otherwise refuse to write it
    at all."""
    return {k: v for k, v in _flatten_numeric(obj).items() if math.isfinite(v) and v >= 0}


def _usage(events):
    """Every numeric usage field an event reports, including nested ones. Codex's own "turn.completed"
    usage is a running total across the whole thread - confirmed on real session records, it only ever
    increases across `codex exec resume` - so only the LAST such event's numbers count for a multi-turn
    run; summing every "turn.completed" event the way this used to would multiply a run's real spend by
    its number of follow-ups. Claude's own per-call "usage" on a "result" event is not a running total
    (each follow-up reports only that turn's own tokens, confirmed the same way), so those ARE summed
    across turns; that event's own top-level total_cost_usd (not nested under "usage"), though, IS already
    a running total across `--continue` on the same real records, so only the last one counts too, folded
    in under that same name rather than summed."""
    total, last_turn = {}, None
    for e in events:
        t = e.get("type")
        if t == "turn.completed":
            last_turn = _sane_numeric(e.get("usage"))
        elif t == "result":
            for k, v in _sane_numeric(e.get("usage")).items():
                total[k] = total.get(k, 0) + v
            cost = e.get("total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
                total["total_cost_usd"] = cost
    if last_turn is not None:
        total.update(last_turn)
    return total


# ---------------------------------------------------------------- checks and judge

_CHECK_LOAD = threading.Lock()


def _load_checks(spec):
    """Load a scenario's check.py from its current files, including helpers it imports from beside
    the scenarios, so checks edited while a trial runs never mix with stale cached helpers."""
    path = Path(spec["dir"]) / "check.py"
    if not path.exists():
        return None
    mod_spec = importlib.util.spec_from_file_location(f"trial_check_{spec['name']}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise TrialError(f"cannot load {path}")
    root = Path(spec["dir"]).resolve().parent
    with _CHECK_LOAD:
        for name, m in list(sys.modules.items()):
            f = getattr(m, "__file__", None)
            if f and Path(f).resolve().is_relative_to(root):
                del sys.modules[name]
        mod = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(mod)
    return mod


def _checks_for(spec, run):
    """The check module (or None) and the run's checks; a check that fails to load or raises is
    reported on that run as check_error, which makes the run invalid rather than failed."""
    try:
        mod = _load_checks(spec)
    except Exception as exc:
        return None, {"check_error": f"loading check.py: {type(exc).__name__}: {exc}"}
    try:
        return mod, (mod.check(run) if mod else {})
    except Exception as exc:
        return mod, {"check_error": f"{type(exc).__name__}: {exc}"}


def _judge_evidence(spec: dict, run: "Run") -> tuple[str, str | None]:
    """A scenario's check.py-supplied judge_context for one run - the same evidence a per-run judge sees -
    and, when it could not be produced, why: "" and no error when the scenario has no check.py or no
    judge_context at all, "" and the exception's text when one is defined but raises (an evidence failure
    should not block pairwise judging the way it makes a per-run judge_run call an error, since pairwise
    is comparing existing finished runs, not scoring a fresh one - but the caller uses the error to keep
    the comparison symmetric rather than silently giving only one side evidence)."""
    try:
        mod = _load_checks(spec)
        return (mod.judge_context(run) if mod and hasattr(mod, "judge_context") else ""), None
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


JUDGE_SCHEMA = {"type": "object", "additionalProperties": False,
                "required": ["verdict", "reason"],
                "properties": {"verdict": {"type": "string", "enum": ["pass", "fail", "unclear"]},
                               "reason": {"type": "string"}}}


def _own(path: Path):
    """Give the owner rwx on path when it is a real directory (an agent can lock directories it leaves)."""
    with contextlib.suppress(OSError):
        st = os.lstat(path)
        if stat.S_ISDIR(st.st_mode):
            os.chmod(path, stat.S_IMODE(st.st_mode) | 0o700)


def _reclaim(path: Path):
    """_own every real directory under path, never following a link."""
    stack = [path]
    while stack:
        d = stack.pop()
        _own(d)
        with contextlib.suppress(OSError):
            if stat.S_ISDIR(os.lstat(d).st_mode):
                stack.extend(Path(e.path) for e in os.scandir(d) if e.is_dir(follow_symlinks=False))


def _remove(path: Path):
    """Remove what is at path: a link or file is unlinked, never followed; a directory is removed with its
    contents, whatever permissions an agent left on it."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(st.st_mode):
        _reclaim(path)
        try:
            shutil.rmtree(path)
        except (OSError, RecursionError):  # deeper than a path can name, for example: move it aside
            _own(path.parent)
            os.rename(path, path.with_name(f".discarded-{path.name}-{os.urandom(4).hex()}"))
    else:
        path.unlink()


def _fresh_dir(path: Path) -> Path:
    """An empty directory at path, replacing whatever an agent left there. Missing parents (an opaque judge
    or pairwise cell's own .cells/ directory, the first time one is made) are created too."""
    _remove(path)
    path.mkdir(parents=True)
    return path


def _judge_confinement(jd: Path, readable: list[Path], spec: dict, out: Path) -> list[str]:
    """The judge reads text an agent wrote, so it is confined the same way its scenario resolved (never a
    silent unconfined fallback when bubblewrap is missing, and never dropped by a Codex-native "sandbox"
    value meant only for the agent's own -s flag): with the user's home hidden, able to write only its own
    directory, so the run's record and results stay out of its reach."""
    return [] if _unconfined(spec) else confine_prefix(jd, readable, chdir=jd / "work", out=out)


DEFAULT_JUDGE_ROLE = "You are judging one run of the task below."


def _read_jsonl(path: Path) -> list[dict]:
    return [e for line in _read(path, follow=False).splitlines()
            for e in [_try_json(line)] if isinstance(e, dict)]


def _try_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _judge_cell_dir(out: Path, job_id: str, name: str) -> Path:
    """An opaque, per-run judge working directory that names neither the arm nor the scenario - the same
    reason pairwise's own per-pair cell directories are opaque (see pairwise): some agent CLIs put their
    own working directory into the model's context, which would otherwise tell the judge which arm or
    scenario produced the text it is reading. `name` ("judge" for a fresh run, or recheck's own
    ever-changing "judge.next.<current cell>" - see recheck's _next_name) keeps the current and the
    not-yet-committed verdict in different cells, on every rejudge, not just the first."""
    cell = hashlib.sha256(f"{job_id}\0{name}".encode()).hexdigest()[:16]
    return out / "judges" / ".cells" / cell


def judge_run(plan, spec, run: Run, checks_mod, job_id: str, out: Path, name="judge") -> tuple[dict | None, str | None]:
    """Blind verdict on one run, kept under an opaque out/judges/.cells/<cell> directory (see
    _judge_cell_dir) that reveals neither the arm nor the scenario the way job_id itself would: the judge
    sees the task and evidence, never the arm. The actual work happens one level below the cell itself
    (cell/judge/work), exactly as pairwise nests order-1/order-2 below its own per-pair cell: unconfined
    (see _unconfined), a CLI reaching two directories up from its own cwd lands on this one run's own cell,
    never the .cells directory every run's cell sits in side by side, which an unconfined escape could
    otherwise lock or litter for every other run in the directory. Returns (verdict, cell); a person looks
    the transcript up from the run's own result.json, which records `cell` as "judge_cell" - the same
    convention pairwise uses. Both are None when the scenario asks no judge question or no judge is named."""
    j = spec.get("judge")
    if not j or not plan.get("judge"):
        return None, None
    cell = _fresh_dir(_judge_cell_dir(out, job_id, name))
    jd = cell / "judge"
    jd.mkdir()
    (jd / "work").mkdir()
    (jd / "harness").mkdir()
    env = isolated_env(jd, out, spec, plan["judge"])
    try:
        evidence = checks_mod.judge_context(run) if checks_mod and hasattr(checks_mod, "judge_context") else ""
    except Exception as exc:
        reason = f"judge_context: {type(exc).__name__}: {exc}"
        (jd / "stderr.log").write_text(reason + "\n")
        return {"verdict": "error", "reason": reason}, cell.name
    role = spec.get("judge_role") or DEFAULT_JUDGE_ROLE
    prompt = (
        role + " You see the task it was given, its final message, and evidence about the resulting "
        "state. Judge only the question below against this evidence.\n\n<task>\n" + spec["prompt"] + "\n</task>\n\n"
        + "".join(f"<followup>\n{f}\n</followup>\n\n" for f in spec.get("followups", []))
        + "<final_message>\n" + run.final_message.strip() + "\n</final_message>\n\n"
        + ("<evidence>\n" + evidence.strip() + "\n</evidence>\n\n" if evidence else "")
        + "<question>\n" + j["question"] + "\n</question>\n\n"
        + "verdict is 'pass' when " + j["pass_when"] + "; 'fail' when it clearly does not; 'unclear' "
        "only when the evidence cannot decide. reason is one sentence of at most 40 words."
    )
    verdict, usage = _judge_call(dict(plan["judge"]), spec, prompt, JUDGE_SCHEMA, jd, env, out)
    _prune(jd)  # a copy_auth login file (or any other per-run cache) is removed whether or not a verdict came back
    if verdict is None or not isinstance(verdict.get("verdict"), str):
        return {"verdict": "error", "reason": "judge produced no verdict"}, cell.name
    if usage:
        verdict["usage"] = usage
    return verdict, cell.name


def _judge_call(jarm: dict, spec: dict, prompt: str, schema: dict, jd: Path, env: dict, out: Path) -> tuple[dict | None, dict]:
    """One blind judge call (codex or claude), constrained to `schema`, confined the same way a run's own
    judge is; writes prompt.md and its native record under `jd`, exactly as judge_run always has. Returns
    the parsed verdict object (or None when the judge produced nothing, however it failed to) and its usage
    - the caller decides which key the schema's decision lives under and what "no verdict" means for it."""
    (jd / "prompt.md").write_text(prompt)
    judge_events: list[dict] = []
    if jarm["executor"] == "codex":
        schema_path = jd / "schema.json"
        schema_path.write_text(json.dumps(schema))
        home = jd / "home"
        home.mkdir()
        (home / "config.toml").write_text(_provider_config(jarm["model"], jarm.get("effort", "high")))
        cache = CODEX_HOME_SRC / "models_cache.json"
        if cache.exists():
            shutil.copy(cache, home / "models_cache.json")
        _copy_auth("codex", jarm, home, "judge using codex")
        codex = _resolve_binary("codex", jarm, "TRIAL_CODEX_BIN")
        var = jarm.get("api_key_var") or _default_key_var("codex")
        key_prefix, key_env = _resolve_key(jarm, var, var, "judge using codex")
        env = dict(env, **key_env)
        readable = _executor_readable(codex) + [Path(p).expanduser() for p in jarm.get("readable", [])]
        env["PATH"] = _extend_path(env.get("PATH", ""), readable)
        cmd = key_prefix + _judge_confinement(jd, readable, spec, out) + [
            codex, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-m", jarm["model"],
            "-c", f"model_reasoning_effort={jarm.get('effort', 'high')}", "-C", str(jd / "work"),
            "--output-schema", str(schema_path), "-o", str(jd / "verdict.json"), "-"]
        _run(cmd, cwd=jd / "work", env=dict(env, CODEX_HOME=str(home)), stdin_text=prompt,
             timeout=600, stdout_path=jd / "events.jsonl", stderr_path=jd / "stderr.log")
        _own(jd)
        judge_events = _read_jsonl(jd / "events.jsonl")
    elif jarm["executor"] == "claude":
        jenv, prefix = _claude_proxy(jarm, env)
        _copy_auth("claude", jarm, Path(jenv["HOME"]), "judge using claude")
        binary = _resolve_binary("claude", jarm, "TRIAL_CLAUDE_BIN")
        readable = _executor_readable(binary) + [Path(p).expanduser() for p in jarm.get("readable", [])]
        jenv["PATH"] = _extend_path(jenv.get("PATH", ""), readable)
        cmd = prefix + _judge_confinement(jd, readable, spec, out) + [binary, "-p", "--bare", "--model", jarm["model"],
                        "--output-format", "json", "--json-schema", json.dumps(schema)]
        if jarm.get("effort"):
            cmd += ["--effort", jarm["effort"]]
        _run(cmd, cwd=jd / "work", env=jenv, stdin_text=prompt, timeout=600,
             stdout_path=jd / "verdict.raw.json", stderr_path=jd / "stderr.log")
        _own(jd)
        raw = _read(jd / "verdict.raw.json", follow=False)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                judge_events = [parsed]
            _write_atomic(jd / "verdict.json", json.dumps(parsed.get("structured_output") or json.loads(parsed["result"])).encode())
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError, OSError):
            pass
    try:
        verdict = json.loads(_read(jd / "verdict.json", follow=False))
    except json.JSONDecodeError:
        verdict = None
    if not isinstance(verdict, dict):
        return None, {}
    return verdict, _usage(judge_events)


# ---------------------------------------------------------------- pairwise judging

PAIRWISE_SCHEMA = {"type": "object", "additionalProperties": False,
                   "required": ["winner", "reason"],
                   "properties": {"winner": {"type": "string", "enum": ["1", "2", "tie"]},
                                  "reason": {"type": "string"}}}


def _pairwise_prompt(spec: dict, j: dict, first: str, second: str, evidence_first: str = "",
                     evidence_second: str = "") -> str:
    """Two outputs shown in an arbitrary order, with no name or hint of which arm made which - only their
    own text, each one's own check.py-supplied evidence about the resulting state (the same evidence a
    per-run judge gets), and the scenario's judge question, so the verdict cannot depend on where an
    output came from."""
    role = spec.get("judge_role") or DEFAULT_JUDGE_ROLE
    return (
        role + " You are comparing two responses to the same task, shown to you in an arbitrary order with "
        "no indication of their source. Judge only the question below.\n\n<task>\n" + spec["prompt"] + "\n</task>\n\n"
        + "".join(f"<followup>\n{f}\n</followup>\n\n" for f in spec.get("followups", []))
        + "<response_1>\n" + first.strip() + "\n</response_1>\n\n"
        + (f"<evidence_1>\n{evidence_first.strip()}\n</evidence_1>\n\n" if evidence_first else "")
        + "<response_2>\n" + second.strip() + "\n</response_2>\n\n"
        + (f"<evidence_2>\n{evidence_second.strip()}\n</evidence_2>\n\n" if evidence_second else "")
        + "<question>\n" + j["question"] + "\n</question>\n\n"
        + "winner is '1' when response 1 better meets the question, '2' when response 2 does, 'tie' when "
        "they are equally good or the evidence cannot decide. reason is one sentence of at most 40 words."
    )


def _pairwise_order(jarm: dict, spec: dict, out: Path, jd: Path, prompt: str) -> dict:
    """One presentation order's verdict, confined and recorded under `jd` exactly like a per-run judge."""
    jd.mkdir(parents=True)
    (jd / "work").mkdir()
    (jd / "harness").mkdir()
    env = isolated_env(jd, out, spec, jarm)
    verdict, usage = _judge_call(dict(jarm), spec, prompt, PAIRWISE_SCHEMA, jd, env, out)
    _prune(jd)  # a copy_auth login file (or any other per-run cache) is removed on every pairwise order, pass or fail
    if verdict is None or not isinstance(verdict.get("winner"), str):
        return {"winner": "error", "reason": "judge produced no verdict"}
    if usage:
        verdict["usage"] = usage
    return verdict


def _pair_outcome(v1: dict, v2: dict) -> str:
    """v1 judges (a, b) in that order (winner '1' means a won); v2 judges (b, a) (winner '1' means b won). A
    pair is decisive and consistent only when both orders name the same arm; any disagreement between the
    two orders - including a tie against a decisive verdict - is order-inconsistent, never averaged away. A
    verdict outside the schema's enum (the judge errored) makes the whole pair invalid."""
    if v1.get("winner") not in ("1", "2", "tie") or v2.get("winner") not in ("1", "2", "tie"):
        return "invalid"
    winner1 = {"1": "a", "2": "b", "tie": "tie"}[v1["winner"]]
    winner2 = {"1": "b", "2": "a", "tie": "tie"}[v2["winner"]]
    if winner1 == winner2:
        return {"a": "a_wins", "b": "b_wins", "tie": "tie"}[winner1]
    return "inconsistent"


def _judge_pair(plan_judge: dict, spec: dict, out: Path, cell_dir: Path, arm_a: str, ra: dict, arm_b: str, rb: dict) -> dict:
    """Both orders of one matched pair (same scenario, same repeat): the judge sees each output's own final
    message and check.py evidence (the same text and evidence a per-run judge would see, including a
    scenario's own "artifact" override), and never the arm names - which this function alone still knows -
    or the scenario name: `cell_dir` is an opaque, arm- and scenario-blind directory (see `pairwise`), never
    the human-readable one a person would look the pair up by, since some agent CLIs put their own working
    directory into the model's context."""
    unconfined = _unconfined(spec)
    run_a = Run(out / "runs" / ra["job"], ra["status"], unconfined=unconfined, artifact=spec.get("artifact"))
    run_b = Run(out / "runs" / rb["job"], rb["status"], unconfined=unconfined, artifact=spec.get("artifact"))
    (ev_a, err_a), (ev_b, err_b) = _judge_evidence(spec, run_a), _judge_evidence(spec, run_b)
    if err_a or err_b:
        # An evidence failure on either side must never leave the comparison skewed toward whichever side
        # still has evidence; give neither side any, and record why on the pair for a person to see.
        ev_a = ev_b = ""
    j = spec["judge"]
    _fresh_dir(cell_dir)
    v1 = _pairwise_order(plan_judge, spec, out, cell_dir / "order-1",
                         _pairwise_prompt(spec, j, run_a.final_message, run_b.final_message, ev_a, ev_b))
    v2 = _pairwise_order(plan_judge, spec, out, cell_dir / "order-2",
                         _pairwise_prompt(spec, j, run_b.final_message, run_a.final_message, ev_b, ev_a))
    result = {"scenario": spec["name"], "arms": [arm_a, arm_b], "repeat": ra["repeat"], "outcome": _pair_outcome(v1, v2),
             "cell": cell_dir.name,
             "orders": [{"order": [arm_a, arm_b], "verdict": v1}, {"order": [arm_b, arm_a], "verdict": v2}]}
    if err_a or err_b:
        result["evidence_errors"] = {k: v for k, v in {"a": err_a, "b": err_b}.items() if v}
    return result


def _pair_jobs(out: Path, plan: dict, arm_a: str, arm_b: str) -> list[tuple[dict, dict, dict]]:
    """(scenario spec, a's result, b's result) for every (scenario, repeat) both arms finished ok with a
    scenario judge question to ask - the matched runs pairwise judging compares."""
    specs = {s["name"]: _effective_sandbox(plan, _current(s)) for s in plan.get("scenarios", [])}
    loaded, _ = _load_results(out)
    by_key: dict[tuple, dict] = {}
    for _, r in loaded:
        by_key.setdefault((r["scenario"], r["repeat"]), {})[r["arm"]] = r
    pairs = []
    for (scenario, _repeat), by_arm in sorted(by_key.items()):
        spec = specs.get(scenario)
        if not spec or not spec.get("judge") or arm_a not in by_arm or arm_b not in by_arm:
            continue
        ra, rb = by_arm[arm_a], by_arm[arm_b]
        if ra["status"] != "ok" or rb["status"] != "ok":
            continue
        pairs.append((spec, ra, rb))
    return pairs


def _pairwise_stats(pairs: list[dict]) -> dict:
    """A's win rate (with a Wilson interval) is over decisive AND consistent pairs only - ties, order
    flips, and judge errors are reported but never folded into it."""
    counts = {"a_wins": 0, "b_wins": 0, "tie": 0, "inconsistent": 0, "invalid": 0}
    for p in pairs:
        counts[p["outcome"]] += 1
    decisive = counts["a_wins"] + counts["b_wins"]
    lo, hi = wilson(counts["a_wins"], decisive)
    return {**counts, "pairs": len(pairs), "decisive": decisive,
            "a_win_rate": (counts["a_wins"] / decisive) if decisive else None,
            "a_win_rate_interval": [lo, hi] if decisive else None}


def pairwise(out: Path, arm_a: str, arm_b: str, judge: dict, jobs: int = 6) -> dict:
    """Blind pairwise judging of two arms' matched runs, in both presentation orders. Writes each pair's
    verdicts to out/pairwise/<a>__<b>/<scenario>__r<n>.json (a person's index of the pairs), the actual
    judge transcripts to an opaque out/pairwise/.cells/ directory a pair's record names but that never
    itself names an arm or scenario, and the aggregate this returns to out/pairwise/<a>__<b>.json, where
    `summarize` and `report` both pick it up."""
    if not (out / "plan.json").exists():
        raise TrialError(f"{out} has no plan.json; name a directory that `trial.py run` wrote")
    with _lock(out):
        plan = _stored_plan(out)
        if arm_a == arm_b:
            raise TrialError("pairwise needs two different arm names")
        missing = [n for n in (arm_a, arm_b) if n not in plan.get("arms", {})]
        if missing:
            raise TrialError(f"{out} has no arm {', '.join(missing)}; valid arms: " + ", ".join(sorted(plan.get("arms", {}))))
        pending = _pair_jobs(out, plan, arm_a, arm_b)
        if not pending:
            raise TrialError(f"no matched, finished runs of '{arm_a}' and '{arm_b}' with a scenario judge "
                             f"question under {out}")
        pair_dir = out / "pairwise" / f"{arm_a}__{arm_b}"
        pair_dir.mkdir(parents=True, exist_ok=True)
        (out / "pairwise" / ".cells").mkdir(parents=True, exist_ok=True)

        def one(item):
            spec, ra, rb = item
            pair_id = f"{spec['name']}__r{ra['repeat']}"
            cell = hashlib.sha256(f"{arm_a}\0{arm_b}\0{pair_id}".encode()).hexdigest()[:16]
            cell_dir = out / "pairwise" / ".cells" / cell
            result = _judge_pair(judge, spec, out, cell_dir, arm_a, ra, arm_b, rb)
            _write_json(pair_dir / f"{pair_id}.json", result)
            return result

        with cf.ThreadPoolExecutor(jobs) as pool:
            results = list(pool.map(one, pending))
        summary = {"arms": [arm_a, arm_b], "judge": _identity(judge, JUDGE_FIELDS),
                  "overall": _pairwise_stats(results),
                  "scenarios": {s: _pairwise_stats([r for r in results if r["scenario"] == s])
                                for s in sorted({r["scenario"] for r in results})}}
        _write_json(out / "pairwise" / f"{arm_a}__{arm_b}.json", summary)
        return summary


def _load_pairwise(out: Path) -> dict:
    """Every pairwise aggregate summary under out/pairwise/, keyed "a__b" - the shape `pairwise()` returns,
    picked out from the per-pair detail files (which lack "overall") that share the same directory."""
    d = out / "pairwise"
    found = {}
    if not d.is_dir():
        return found
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(_read(p, follow=False))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("overall"), dict) and isinstance(data.get("arms"), list):
            found["__".join(data["arms"])] = data
    return found


def _pairwise_report(summary: dict) -> str:
    a, b = summary["arms"]
    jm = summary["judge"].get("model", summary["judge"].get("executor"))
    lines = [f"Pairwise: {a} vs {b} (judge {jm})", ""]
    for scope, st in [("overall", summary["overall"]), *sorted(summary["scenarios"].items())]:
        if st["a_win_rate"] is None:
            rate = "n/a"
        else:
            lo, hi = st["a_win_rate_interval"]
            rate = f"{st['a_win_rate']:.0%} ({lo:.0%}-{hi:.0%})"
        invalid = f" - invalid {st['invalid']}" if st["invalid"] else ""
        lines.append(f"{scope}: {a} {st['a_wins']} - {b} {st['b_wins']} - tie {st['tie']} - "
                     f"inconsistent {st['inconsistent']}{invalid}; {a} win rate {rate} over {st['decisive']} "
                     "decisive pairs")
    return "\n".join(lines)


# ---------------------------------------------------------------- environment

# Always allowed by name, on top of PATH, HOME, and TMPDIR (each rebuilt below), an arm's own "pass_env",
# and the one API key variable the arm uses (added separately, where each executor resolves it).
ALWAYS_ALLOWED_ENV = ("LANG", "TERM", "TZ", "USER", "LOGNAME")


def _copy_readonly(src: Path, dst: Path) -> None:
    """A read-only copy of `src` (a file or a directory tree) at `dst`, for a "resources" entry (see
    _with_resources): the agent can read a resource - a skill, a reference doc - but every write bit is
    cleared on the copy, never the original, so it cannot rewrite the very thing a check might compare
    its work against."""
    if src.is_dir():
        shutil.copytree(src, dst, symlinks=True)
        for p in [dst, *dst.rglob("*")]:
            if not p.is_symlink():
                os.chmod(p, stat.S_IMODE(os.lstat(p).st_mode) & ~0o222)
    else:
        shutil.copy2(src, dst)
        os.chmod(dst, stat.S_IMODE(os.lstat(dst).st_mode) & ~0o222)


def isolated_env(job_dir: Path, out: Path, spec, arm: dict | None = None):
    """An explicit allowlist, never the parent environment minus a scrub list: PATH (rebuilt from the
    scenario's tools and system directories, plus the parent PATH when this run resolved to "sandbox":
    "none"), a throwaway HOME and TMPDIR (always the run's own, never the real ones), locale and terminal
    identity (LANG, LC_*, TERM, TZ, USER, LOGNAME), any names `arm` lists in "pass_env", and git and gh
    configuration private to the run. The one API key variable an executor uses is added by that executor,
    not here.

    Scenario tools are copied into the run so their location reveals nothing about the scenario's checks.
    """
    sdir = Path(spec["dir"])
    tools = job_dir / "tools"
    tools.mkdir(exist_ok=True)
    for rel in spec.get("bin", ["bin"]):
        src = sdir / rel
        if src.is_dir():
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, tools / f.name)
    allow = set(ALWAYS_ALLOWED_ENV) | {k for k in os.environ if k.startswith("LC_")} | set((arm or {}).get("pass_env", []))
    env = {k: v for k, v in os.environ.items() if k in allow}
    harness = job_dir / "harness"
    unconfined = _unconfined(spec)
    path = os.pathsep.join([str(tools), *SYSTEM_PATH])
    if unconfined:  # no confinement to punch holes in, so the parent PATH is forwarded verbatim (unfiltered)
        parent_path = os.environ.get("PATH", "")
        if parent_path:
            path = os.pathsep.join([path, parent_path])
    env.update(TRIAL_HARNESS=str(harness), GIT_CEILING_DIRECTORIES=str(out), GIT_CONFIG_NOSYSTEM="1",
               GH_CONFIG_DIR=str(harness / ".gh"), PATH=path, GIT_TERMINAL_PROMPT="0")
    gitconfig = harness / ".gitconfig"
    gitconfig.write_text("[user]\n\tname = Acme Dev\n\temail = dev@acme.example\n"
                         "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
                         "[tag]\n\tgpgsign = false\n")
    env["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    tmp = harness / "tmp"
    tmp.mkdir(exist_ok=True)
    env["TMPDIR"] = str(tmp)
    home = harness / "home"
    home.mkdir(exist_ok=True)
    for rel, src in (arm or {}).get("resources", {}).items():
        dest = home / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        _copy_readonly(Path(src), dest)
    shutil.copy(gitconfig, home / ".gitconfig")
    env["HOME"] = str(home)
    return env


# ---------------------------------------------------------------- one job

MIN_FREE_BYTES = int(os.environ.get("TRIAL_MIN_FREE_GB", "5")) * 1024 ** 3
# A judge's own opaque cell directory (see _judge_cell_dir) is, from isolated_env's point of view, a job
# directory in its own right - it gets a "home" and a "harness" of its own the same way - so the same
# relative paths prune it too.
PRUNE = ("home/.tmp", "home/skills", "home/models_cache.json", "home/auth.json",
         "harness/home/.cache", "harness/home/.claude/.credentials.json")


def _prune(job_dir: Path, rels=PRUNE):
    """Remove per-run caches that hold no evidence (host plugin catalogs, bundled skill copies, a
    copy_auth login file once the run is over). A path through a link an agent planted is skipped, and a
    link in a cache's place is removed, never its target."""
    for rel in rels:
        target = job_dir
        for part in Path(rel).parts[:-1]:
            target = target / part
            if target.is_symlink() or not target.is_dir():
                break
        else:
            with contextlib.suppress(OSError):  # pruning only saves space
                _remove(target / Path(rel).name)


def _check_space(out: Path):
    free = shutil.disk_usage(out).free
    if free < MIN_FREE_BYTES:
        raise TrialError(f"only {free // 1024 ** 2} MiB free on {out}; stopping before the disk fills "
                         f"(set TRIAL_MIN_FREE_GB to change the {MIN_FREE_BYTES // 1024 ** 3} GiB floor)")

TRANSPORT = ("502 Bad Gateway", "503 Service", "failed to connect", "Connection reset", "stream disconnected",
             "ECONNRESET", "rate limit", "429 Too Many")


def run_job(plan, out: Path, job, retry_invalid=False, attempts=3):
    """Run one job; a run that fails in transport before producing a result is retried fresh."""
    for attempt in range(attempts):
        result = _run_job_once(plan, out, job, retry_invalid or attempt > 0)
        stderr = _read(out / "runs" / result["job"] / "stderr.log", follow=False)
        if result["status"] == "ok" or not any(t in stderr for t in TRANSPORT):
            return result
    return result


def _effective_sandbox(plan: dict, spec: dict) -> dict:
    """`spec` with its effective sandbox mode resolved: the scenario's own "sandbox" wins over the plan's
    (or --sandbox's) default, which is "confined" unless explicitly lowered."""
    return dict(spec, sandbox=spec.get("sandbox", plan.get("sandbox", "confined")))


def _needs_bwrap(plan: dict) -> bool:
    """Whether running this plan as given would need bubblewrap at all: every scenario whose effective
    sandbox is not the literal "none" needs it - for checks, git, and a judge at least, and for a codex
    arm's own default confinement too (see _unconfined). Checked once, before anything is scheduled, so a
    missing bwrap is refused before any scenario's setup.sh has run or plan.json has been written - not
    discovered mid-run, per job, the way it otherwise first surfaces only when that job's own executor or
    check actually needs it."""
    return any(not _unconfined(_effective_sandbox(plan, spec)) for spec in plan["scenarios"])


def _run_job_once(plan, out: Path, job, retry_invalid):
    arm_name, raw_spec, rep = job
    arm = dict(plan["arms"][arm_name])
    spec = _effective_sandbox(plan, raw_spec)
    job_id = f"{spec['name']}__{arm_name}__r{rep}"
    job_dir = out / "runs" / job_id
    result_path = job_dir / "result.json"
    # Marks an attempt in progress, outside the directory the agent can write: a result.json found while it
    # exists was never finished by the runner (the agent may have written it).
    pending = out / "runs" / f"{job_id}.pending"
    if os.path.lexists(result_path) and not pending.exists():
        try:
            previous = json.loads(_read(result_path, follow=False))
        except json.JSONDecodeError:
            previous = None
        if not isinstance(previous, dict):
            previous = {"passed": None}  # an interrupted write: run the job again
            retry_invalid = True
        if not (retry_invalid and previous.get("passed") is None):
            return previous
    _check_space(out)
    _remove(job_dir)  # a partial earlier attempt; results are never mixed
    (out / "runs").mkdir(exist_ok=True)
    pending.touch()
    (job_dir / "work").mkdir(parents=True)
    (job_dir / "harness").mkdir()
    sdir = Path(spec["dir"])
    if (sdir / "fixture").is_dir():
        shutil.copytree(sdir / "fixture", job_dir / "work", dirs_exist_ok=True, ignore=_skip_for_copy)
    env = isolated_env(job_dir, out, spec, arm)
    setup_started = dt.datetime.now(dt.timezone.utc)
    if (sdir / "setup.sh").exists():
        r = subprocess.run(["sh", str(sdir / "setup.sh")], cwd=job_dir / "work", env=env,
                           capture_output=True, text=True, timeout=300)
        (job_dir / "setup.log").write_text(r.stdout + r.stderr)
        if r.returncode != 0:
            result = {"job": job_id, "arm": arm_name, "scenario": spec["name"], "repeat": rep,
                      "status": "setup-failed", "passed": None, "identity": _identity(arm)}
            _write_json(result_path, result)
            pending.unlink()
            return result
    setup_seconds = round((dt.datetime.now(dt.timezone.utc) - setup_started).total_seconds(), 1)
    agent_started = dt.datetime.now(dt.timezone.utc)
    status, confined = EXECUTORS[arm["executor"]](arm, spec, job_dir, env)
    # The executor's own wall time only, never setup, checks, or judging (each timed and recorded on its
    # own below): those phases can dwarf or shrink independently of what the arm itself actually spent.
    seconds = round((dt.datetime.now(dt.timezone.utc) - agent_started).total_seconds(), 1)
    _own(job_dir)  # the runner writes here next, whatever the agent did to it
    unconfined = _unconfined(spec)
    run = Run(job_dir, status, unconfined=unconfined, artifact=spec.get("artifact"))
    checks_started = dt.datetime.now(dt.timezone.utc)
    checks_mod, checks = _checks_for(spec, run)
    checks_seconds = round((dt.datetime.now(dt.timezone.utc) - checks_started).total_seconds(), 1)
    judge_started = dt.datetime.now(dt.timezone.utc)
    verdict, judge_cell = judge_run(plan, spec, run, checks_mod, job_id, out) if "check_error" not in checks else (None, None)
    judge_seconds = round((dt.datetime.now(dt.timezone.utc) - judge_started).total_seconds(), 1)
    required = spec.get("required", [])
    passed = None
    judge_missing = False
    if status == "ok" and "check_error" not in checks:
        passed = all(checks.get(name) is True for name in required)
        if spec.get("judge") and spec.get("judge_required", True):
            if not plan.get("judge"):  # a judge question with no judge to ask: invalid, never a silent pass
                passed, judge_missing = None, True
            else:
                v = (verdict or {}).get("verdict")
                passed = None if v == "error" else passed and v == "pass"
    result = {"job": job_id, "arm": arm_name, "scenario": spec["name"], "repeat": rep, "status": status,
              "passed": passed, "checks": checks, "judge": verdict, "usage": run.usage,
              "commands": len(run.commands), "seconds": seconds, "setup_seconds": setup_seconds,
              "checks_seconds": checks_seconds, "judge_seconds": judge_seconds,
              "sandbox": spec.get("sandbox", "confined"), "confined": confined, "identity": _identity(arm)}
    if run.artifact_missing:
        result["artifact_missing"] = True
    if judge_missing:
        result["judge_missing"] = True
    if verdict is not None:
        result["judge_identity"] = _identity(plan["judge"], JUDGE_FIELDS)
        result["judge_cell"] = judge_cell
    _write_json(result_path, result)
    pending.unlink()
    _prune(job_dir)
    return result


def derive(out: Path, scenario: str, artifact: str, consumer: Path, base: dict, repeats: int, plan_path: Path) -> int:
    """A second-stage plan: each artifact an earlier run produced becomes an arm's instructions.

    Each derived arm's executor settings start from what its own source run actually recorded (so a
    two-stage trial reuses the same model by default, per source arm, rather than a guessed default), with
    `base` (--executor) overriding or extending them. An agent executor left with no model this way - an
    older result recorded none, or `base` names none either - is an error naming --executor as the fix.

    Arm names are '<source arm>~r<repeat>', so `summarize --group` pools each source arm's artifacts."""
    base = dict(base or {})
    env_file = base.get("env_file")
    if isinstance(env_file, str) and env_file and "${" not in env_file and not Path(env_file).expanduser().is_absolute():
        base["env_file"] = os.path.relpath(Path(env_file).resolve(), plan_path.parent.resolve())  # plans read it plan-relative
    arms_dir = plan_path.parent / (plan_path.stem + "-arms")
    arms_dir.mkdir(parents=True, exist_ok=True)
    arms = {}
    for path, result in _load_results(out)[0]:
        if result.get("scenario") != scenario:
            continue
        work = path.parent / "work"
        produced = work / artifact
        if (result.get("status") != "ok" or work.is_symlink() or not work.is_dir() or produced.is_symlink()
                or not produced.is_file() or not produced.resolve().is_relative_to(path.parent.resolve() / "work")):
            continue
        name = f"{result['arm']}~r{result['repeat']}"
        arm = {**result.get("identity", {}), **base}
        arm.pop("instructions_sha256", None)  # about to point at a new instructions file
        if arm.get("executor") in ("codex", "claude") and not arm.get("model"):
            raise TrialError(f"derived arm '{name}' has no model: its source run's own record names none, and "
                             "--executor did not name one; pass --executor with a \"model\"")
        target = arms_dir / f"{name.replace('~', '__')}.md"
        try:
            data = produced.read_bytes()
        except OSError:
            continue
        target.write_bytes(data)
        arm["instructions"] = str(target.relative_to(plan_path.parent))
        arms[name] = arm
    if not arms:
        raise TrialError(f"no finished '{scenario}' runs with {artifact} under {out / 'runs'}")
    plan = {"name": plan_path.stem, "repeats": repeats, "seed": 1, "arms": arms,
            "scenarios": [os.path.relpath(consumer.resolve(), plan_path.parent.resolve())]}
    plan_path.write_text(json.dumps(plan, indent=1))
    return len(arms)


def recheck(out: Path, rejudge=False, jobs=6, judge=None, only=None, sandbox=None) -> int:
    """Re-score finished runs with the scenarios' current checks, and optionally their current judge.

    Without rejudge, stored judge verdicts are kept. With it, the judge runs again on the stored run
    (its final message and resulting state) using the scenario's current question and evidence.
    `judge` becomes the run directory's judge: it implies rejudge and re-judges every run the judge scores,
    so it refuses before judging anything when one of them cannot be re-judged. A re-judge changes nothing
    when the judge gives no verdict for any run. `sandbox` overrides the directory's plan-level default for
    this and future rechecks (a scenario's own "sandbox" still wins)."""
    if not (out / "plan.json").exists():
        raise TrialError(f"{out} has no plan.json; name a directory that `trial.py run` wrote")
    with _lock(out):
        plan = _stored_plan(out)
        if sandbox is not None:
            plan = dict(plan, sandbox=sandbox)
        specs = {s["name"]: _current(s) for s in plan["scenarios"]}
        loaded, _ = _load_results(out)
        if judge is not None:
            if only and any(r.get("scenario") not in only and r.get("status") == "ok" and (specs.get(r.get("scenario")) or {}).get("judge")
                            for _, r in loaded):
                raise TrialError("--judge becomes the judge of the whole run directory, so it re-judges every run; "
                                 "drop --only, or use a new --out")
            missing = sorted({r.get("scenario") for _, r in loaded if r.get("scenario") not in specs})
            if missing:
                raise TrialError(f"{out} holds runs of scenarios its plan.json does not list ({', '.join(missing)}), which "
                                 "--judge cannot re-judge; run the full plan into the directory first, or use a new --out")
            plan, rejudge = dict(plan, judge=_check_env_file(resolve_arm(_check_judge(judge, "--judge"), "judge", plan), "--judge")), True
        if only:
            loaded = [(path, r) for path, r in loaded if r["scenario"] in only]

        def score(item):
            path, result = item
            spec = specs.get(result["scenario"])
            if not spec or result["status"] == "setup-failed":
                return None
            eff = _effective_sandbox(plan, spec)
            run = Run(path.parent, result["status"], unconfined=_unconfined(eff), artifact=eff.get("artifact"))
            return path, result, eff, _checks_for(eff, run)[1]

        with cf.ThreadPoolExecutor(jobs) as pool:
            scored = [x for x in pool.map(score, loaded) if x]
        broken = sorted(r["job"] for _, r, spec, checks in scored
                        if judge is not None and r["status"] == "ok" and spec.get("judge") and "check_error" in checks)
        if broken:
            raise TrialError(f"--judge re-judges every run, but the checks of {', '.join(broken[:5])}"
                             f"{' and others' if len(broken) > 5 else ''} fail to run; fix them (a plain `trial.py recheck` "
                             "shows the errors), or use a new --out")

        def _next_name(result: dict) -> str:
            """The name judge_run hashes into this rejudge's scratch cell (see _judge_cell_dir): folding
            in the CURRENTLY committed "judge_cell" guarantees it never collides with that cell, which a
            fixed "judge.next" name otherwise would on a second or later --rejudge, once a previous one
            already made "judge.next" the current cell - destroying a committed verdict before knowing
            whether this rejudge will itself succeed. Deterministic (not random) so the exception handler
            below can recompute the very same path to clean it up without needing judge_one's return value."""
            return "judge.next." + (result.get("judge_cell") or "")

        def judge_one(item):
            """A new verdict in a fresh opaque cell (see _judge_cell_dir, _next_name); the stored judge
            stays the one result.json's "judge_cell" names until every verdict is in."""
            path, result, spec, checks = item
            if not (rejudge and result["status"] == "ok" and spec.get("judge") and plan.get("judge") and "check_error" not in checks):
                return None
            _own(path.parent)
            run = Run(path.parent, result["status"], unconfined=_unconfined(spec), artifact=spec.get("artifact"))
            return judge_run(plan, spec, run, _load_checks(spec), result["job"], out, _next_name(result))

        try:
            with cf.ThreadPoolExecutor(jobs) as pool:
                verdicts = list(pool.map(judge_one, scored))  # each is (verdict, cell) or None
            failed = [(item, vc) for item, vc in zip(scored, verdicts) if vc and vc[0] and vc[0].get("verdict") == "error"]
            if failed:
                (path, result, *_), (v, cell) = failed[0]
                log = _read(out / "judges" / ".cells" / cell / "stderr.log", follow=False).strip().splitlines()
                jobs_failed = [item[1]["job"] for item, _ in failed]
                raise TrialError(f"the judge gave no verdict for {', '.join(jobs_failed[:5])}"
                                 f"{' and others' if len(jobs_failed) > 5 else ''} ({result['job']}: {v.get('reason', '')}"
                                 f"{'; stderr: ' + log[-1][:300] if log else ''}); nothing was changed")
        except BaseException:
            for _, result, *_ in scored:
                with contextlib.suppress(OSError):
                    _remove(_judge_cell_dir(out, result["job"], _next_name(result)))
            raise

        def finish(item, verdict_cell):
            path, result, spec, checks = item
            verdict, cell = verdict_cell if verdict_cell else (None, None)
            if verdict is not None:
                old_cell = result.get("judge_cell")
                if old_cell and old_cell != cell:
                    with contextlib.suppress(OSError):
                        _remove(out / "judges" / ".cells" / old_cell)
                result["judge"] = dict(verdict, judge_model=plan["judge"].get("model", plan["judge"]["executor"]))
                result["judge_identity"] = _identity(plan["judge"], JUDGE_FIELDS)
                result["judge_cell"] = cell
            passed = None
            result.pop("judge_stale", None)
            result.pop("judge_missing", None)
            if result["status"] == "ok" and "check_error" not in checks:
                passed = all(checks.get(n) is True for n in spec.get("required", []))
                if spec.get("judge") and spec.get("judge_required", True):
                    if not plan.get("judge"):  # a judge question with no judge to ask: invalid, never a silent pass
                        passed, result["judge_missing"] = None, True
                    elif _judged_by(result, plan["judge"]):
                        v = result["judge"].get("verdict")
                        passed = None if v == "error" else passed and v == "pass"
                    else:  # unjudged, or judged by another judge: invalid until re-judged
                        passed, result["judge_stale"] = None, True
            result.update(checks=checks, passed=passed, rechecked=True, rejudged=bool(rejudge))
            # The confinement checks and the judge actually used for THIS recheck, so a directory rechecked
            # with a different --sandbox does not keep showing the sandbox its original run recorded.
            result["sandbox"] = spec.get("sandbox", "confined")
            _write_json(path, result)
            if verdict is not None:
                _prune(out / "judges" / ".cells" / cell)
            return 1

        with cf.ThreadPoolExecutor(jobs) as pool:
            count = sum(pool.map(finish, scored, verdicts))
        if judge is not None or sandbox is not None:
            plan["resolved"] = _record_resolutions(plan.get("resolved"), [plan["judge"]] if judge is not None else [])
            plan["scenarios"] = [specs.get(sp["name"], sp) for sp in plan["scenarios"]]  # as judged
            _write_json(out / "plan.json", plan)
        return count


def _judged_by(result: dict, judge: dict) -> bool:
    """Whether the result holds a verdict from this judge (older results record at most the judge's model)."""
    if not result.get("judge"):
        return False
    if "judge_identity" in result:
        return _effective(result["judge_identity"], True) == _effective(_identity(judge, JUDGE_FIELDS), True)
    return result["judge"].get("judge_model") in (None, judge.get("model", judge.get("executor")))


def _current(spec: dict | None) -> dict:
    """A stored scenario spec updated from its scenario.json as it is now."""
    if not spec:
        return {}
    try:
        return dict(spec, **json.loads((Path(spec["dir"]) / "scenario.json").read_text()))
    except (OSError, json.JSONDecodeError):
        return spec


# ---------------------------------------------------------------- summary

def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def _arm_usage_means(rs: list[dict]) -> dict:
    """Mean of every numeric usage field these runs report, each averaged only over the runs that report
    it - a field only some runs report (such as a cost only one executor sends) is not diluted by treating
    the rest as zero. `rs` is every run an executor was actually started for, valid or not: a run a check
    or judge later ruled invalid still spent whatever tokens or dollars its usage recorded before that."""
    fields = sorted({k for r in rs for k in r.get("usage", {})})
    means = {}
    for f in fields:
        vals = [r["usage"][f] for r in rs if f in r.get("usage", {})]
        if vals:
            means[f] = sum(vals) / len(vals)
    return means


def _cost_measures(rs: list[dict]) -> dict:
    """usage, commands, and seconds means over every run in `rs` (valid or not - see _arm_usage_means),
    each averaged only over the runs that actually reached that stage (a setup-failed run, for instance,
    never ran the executor and so never has "commands" or "seconds" to contribute), plus how many of
    these runs reported no usage at all - a run whose executor never even started, or whose CLI reported
    none, contributes nothing to usage_mean and is called out here rather than silently thinning the mean."""
    # Commands and seconds come from the runs whose executor reported usage, as usage does: an executor that
    # died at launch spent a fraction of a second, and averaging that in makes a comparison against it absurd.
    ran = [r for r in rs if r.get("usage")]
    commands = [r["commands"] for r in ran if r.get("commands") is not None]
    seconds = [r["seconds"] for r in ran if r.get("seconds") is not None]
    return {"usage_mean": _arm_usage_means(rs), "no_usage": sum(1 for r in rs if not r.get("usage")),
            "commands_mean": (sum(commands) / len(commands)) if commands else None,
            "seconds_mean": (sum(seconds) / len(seconds)) if seconds else None}


def _arm_stats(results: list[dict], arm: str) -> dict:
    rs = [r for r in results if r["arm"] == arm]
    ok = [r for r in rs if r["passed"] is not None]
    return {"passed": sum(1 for r in ok if r["passed"]), "valid": len(ok), "runs": len(rs),
            **_cost_measures(rs)}


def _arm_executors(results: list[dict]) -> dict:
    """Each arm's executor, from the first result that recorded one. Used only to decide whether
    "input_tokens" is a comparable number between two arms (see _pct_vs_baseline): Claude's own
    input_tokens excludes cache reads that Codex's includes, so the same field name means different
    things depending on which CLI reported it."""
    out = {}
    for r in results:
        ex = (r.get("identity") or {}).get("executor")
        if ex and r["arm"] not in out:
            out[r["arm"]] = ex
    return out


def _pct(value, base) -> float | None:
    if value is None or base in (None, 0):
        return None
    return (value - base) / base


def _pct_vs_baseline(results: list[dict], scenarios: list[str], arm: str, baseline: str, arm_executor: dict) -> dict:
    """Percentage differences from the baseline arm, one field at a time: computed per scenario, on that
    scenario's own runs (valid or not - see _cost_measures), and only then aggregated across scenarios as
    {"median": ..., "mean": ..., "n_scenarios": ...} - never a single number pooled from every run across
    every scenario at once, which lets one scenario's mix of expensive, excluded runs flip the sign of the
    whole comparison (see trials.md). A scenario contributes to a field only when both arms have a value
    for it there. "input_tokens" is left out entirely when `arm` and `baseline` used different executors,
    since it is not the same measurement across them."""
    per_scenario: dict[str, dict[str, float]] = {}
    same_executor = arm_executor.get(arm) == arm_executor.get(baseline)
    for s in scenarios:
        a, b = _cost_measures([r for r in results if r["scenario"] == s and r["arm"] == arm]), \
               _cost_measures([r for r in results if r["scenario"] == s and r["arm"] == baseline])
        fields = {}
        for k, v in a["usage_mean"].items():
            if k == "input_tokens" and not same_executor:
                continue
            p = _pct(v, b["usage_mean"].get(k))
            if p is not None:
                fields[k] = p
        for k in ("commands_mean", "seconds_mean"):
            p = _pct(a[k], b[k])
            if p is not None:
                fields[k] = p
        if fields:
            per_scenario[s] = fields
    out = {}
    for field in sorted({f for fs in per_scenario.values() for f in fs}):
        pcts = [fs[field] for fs in per_scenario.values() if field in fs]
        out[field] = {"median": statistics.median(pcts), "mean": sum(pcts) / len(pcts), "n_scenarios": len(pcts)}
    return out


def summarize(out: Path, as_json=False, group=False, baseline=None, strict_baseline=False):
    loaded, skipped = _load_results(out)
    results = [r for _, r in loaded]
    if skipped:
        print(f"note: skipped {skipped} unreadable result files", file=sys.stderr)
    if not results:
        raise TrialError(f"no results under {out / 'runs'}")
    if group:
        for r in results:
            r["arm"] = r["arm"].split("~", 1)[0]
    arms = sorted({r["arm"] for r in results})
    scenarios = sorted({r["scenario"] for r in results})
    table = {}
    for s in scenarios:
        for a in arms:
            rs = [r for r in results if r["scenario"] == s and r["arm"] == a]
            ok = [r for r in rs if r["passed"] is not None]
            k = sum(1 for r in ok if r["passed"])
            table[(s, a)] = {"passed": k, "valid": len(ok), "runs": len(rs),
                             "invalid": sorted({_invalid_reason(r) for r in rs if r["passed"] is None}),
                             "interval": wilson(k, len(ok)),
                             "checks": _check_rates(ok)}
    arm_stats = {a: _arm_stats(results, a) for a in arms}
    arm_executor = _arm_executors(results)
    if baseline and baseline not in arm_stats:
        if strict_baseline:  # an explicit --baseline naming no loaded arm is a mistake worth catching
            raise TrialError(f"--baseline {baseline!r} does not name a loaded arm; valid arms: " + ", ".join(arms))
        baseline = None  # the plan's own stored baseline naming none here (--arms filtered it out, say) is not an error
    pairwise_results = _load_pairwise(out)
    if as_json:
        payload = {"scenarios": {f"{s}|{a}": v for (s, a), v in table.items()}, "arms": arm_stats}
        if baseline:
            payload["baseline"] = baseline
            payload["pct_vs_baseline"] = {a: _pct_vs_baseline(results, scenarios, a, baseline, arm_executor)
                                          for a in arms if a != baseline}
        if pairwise_results:
            payload["pairwise"] = pairwise_results
        return _dumps_finite(payload, "summarize --json")
    lines = [f"# Trial summary: {out.name}", ""]
    plan_default = _stored_plan(out).get("sandbox", "confined")
    # Read from each run's own recorded "sandbox" (added when a run finishes, and updated by a recheck that
    # changed it), not only the directory's current plan-level default: that default can change on a later
    # rerun even though earlier runs already finished unconfined, and a directory can otherwise mix confined
    # and unconfined runs unnoticed. Older results, written before this field existed, fall back to the
    # plan-level default they were made under. "confined" (recorded per run since 2.1.0) is checked too, so
    # the notice is never silenced by a value other than "none" that nonetheless left the arm's own process
    # unconfined (a typo, or an unrelated setting) - a mismatch here would itself be a bug worth surfacing.
    if any(r.get("sandbox", plan_default) == "none" or r.get("confined", True) is False for r in results):
        lines += ["**Unconfined**: at least one run in this directory resolved to \"sandbox\": \"none\" "
                 "(bubblewrap was unavailable, or it was set explicitly, for that run or as the directory's "
                 "default); an unconfined run had the host reachable, not isolated, for its own process, "
                 "checks, git, and judge.", ""]
    lines += ["Passed / valid runs (95% Wilson interval). A run is valid when the executor finished "
             "and its checks ran; invalid runs are listed separately (judge-missing: the scenario asks a "
             "judge question but the plan names no judge; judge-stale: no verdict from the run directory's "
             "judge, which `trial.py recheck --rejudge` gives; judge-error: the judge gave no verdict).", "",
             "| Scenario | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for s in scenarios:
        cells = []
        for a in arms:
            v = table[(s, a)]
            lo, hi = v["interval"]
            cell = f"{v['passed']}/{v['valid']} ({lo:.0%}–{hi:.0%})"
            if v["invalid"]:
                cell += f" · invalid {v['runs'] - v['valid']}: {', '.join(v['invalid'])}"
            cells.append(cell)
        lines.append(f"| {s} | " + " | ".join(cells) + " |")
    lines += [""]
    if baseline:
        lines += [f"Each arm's cost and timing columns show its percentage difference from the baseline "
                 f"arm `{baseline}`, computed per scenario and then given as the median and mean across "
                 f"scenarios (n = how many scenarios both arms have a value for); input tokens carry no "
                 f"percentage between two different executors, since the field means different things to "
                 f"each (Claude's excludes cache reads, Codex's includes them) - the executor is named "
                 f"instead. Usage, commands, and seconds are meant over every run that reported a value, "
                 f"whether or not it later passed; \"no usage\" counts runs an executor reported none for.", ""]
    lines += ["| Arm | passed | valid | mean input tokens | mean output tokens | mean cost | mean commands | "
              "mean seconds | no usage |", "|---|---|---|---|---|---|---|---|---|"]
    base_st = arm_stats.get(baseline) if baseline else None
    pct_by_arm = {a: _pct_vs_baseline(results, scenarios, a, baseline, arm_executor) for a in arms} if baseline else {}

    def fmt_pct(pct: dict | None) -> str:
        if not pct:
            return ""
        return f" ({pct['median']:+.0%} med / {pct['mean']:+.0%} avg, n={pct['n_scenarios']})"

    def cell(value, fmt, field, a):
        if value is None:
            return "–"
        text = fmt.format(value)
        own_baseline = base_st is not None and a == baseline
        if own_baseline or base_st is None:
            return text
        pct = pct_by_arm.get(a, {}).get(field)
        if pct is None and field == "input_tokens":
            fam = arm_executor.get(a)
            return f"{text} ({fam})" if fam and fam != arm_executor.get(baseline) else text
        return text + fmt_pct(pct)

    for a in arms:
        st = arm_stats[a]
        um = st["usage_mean"]
        cells = [cell(um.get("input_tokens"), "{:.0f}", "input_tokens", a),
                cell(um.get("output_tokens"), "{:.0f}", "output_tokens", a),
                cell(um.get("total_cost_usd"), "{:.4f}", "total_cost_usd", a),
                cell(st["commands_mean"], "{:.1f}", "commands_mean", a),
                cell(st["seconds_mean"], "{:.0f}", "seconds_mean", a)]
        lines.append(f"| {a} | {st['passed']} | {st['valid']} | " + " | ".join(cells) + f" | {st['no_usage']} |")
    if pairwise_results:
        lines += ["", "## Pairwise comparisons", "",
                 "Blind head-to-head judging of matched runs (same scenario, same repeat) in both "
                 "presentation orders; a win rate counts only decisive pairs where both orders agreed.", ""]
        for key in sorted(pairwise_results):
            s = pairwise_results[key]
            for line in _pairwise_report(s).splitlines():
                lines.append(line if line == "" else f"- {line}")
            lines.append("")
    lines += ["", "Check rates per scenario and arm (true / valid runs; numbers are means):", ""]
    for s in scenarios:
        names = sorted({n for a in arms for n in table[(s, a)]["checks"]})
        if not names:
            continue
        lines += [f"**{s}**", "", "| Check | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
        for n in names:
            lines.append(f"| {n} | " + " | ".join(table[(s, a)]["checks"].get(n, "–") for a in arms) + " |")
        lines.append("")
    return "\n".join(lines)


def _invalid_reason(r: dict) -> str:
    if r["status"] != "ok":
        return r["status"]
    if r.get("judge_missing"):
        return "judge-missing"
    if r.get("judge_stale"):
        return "judge-stale"
    return "judge-error" if (r.get("judge") or {}).get("verdict") == "error" else "check-error"


def _check_rates(results):
    names = sorted({n for r in results for n in r.get("checks", {})})
    rates = {}
    for n in names:
        vals = [r["checks"].get(n) for r in results if n in r.get("checks", {})]
        if all(isinstance(v, bool) for v in vals):
            rates[n] = f"{sum(vals)}/{len(vals)}"
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            rates[n] = f"{sum(vals) / len(vals):.1f}"
        else:
            rates[n] = "mixed"
    j = [r["judge"]["verdict"] for r in results if r.get("judge")]
    if j:
        rates["judge_pass"] = f"{j.count('pass')}/{len(j)}"
    return rates


# ---------------------------------------------------------------- report

REPORT_EXCERPT_CHARS = 2000  # a run's final message, bounded, so a report stays sized for a visualizer's own budget


def _run_record(path: Path, r: dict, specs: dict) -> dict:
    """One run's record for `report`: identifying fields, validity, its checks and judge verdict, usage
    and timing, and a bounded excerpt of the output that was judged (never the full native record - that
    stays in the run directory itself, which `report` names)."""
    spec = specs.get(r.get("scenario")) or {}
    final = ""
    with contextlib.suppress(OSError):
        final = Run(path.parent, r.get("status", ""), unconfined=_unconfined(spec),
                    artifact=spec.get("artifact")).final_message
    j = r.get("judge") or {}
    return {"job": r.get("job"), "scenario": r.get("scenario"), "arm": r.get("arm"), "repeat": r.get("repeat"),
            "status": r.get("status"), "passed": r.get("passed"), "valid": r.get("passed") is not None,
            "invalid_reason": None if r.get("passed") is not None else _invalid_reason(r),
            "checks": r.get("checks", {}),
            "judge": {"verdict": j.get("verdict"), "reason": j.get("reason")} if j else None,
            "usage": r.get("usage", {}), "commands": r.get("commands"),
            # "seconds" is the executor's own wall time only; setup/checks/judge are each timed separately.
            "seconds": r.get("seconds"), "setup_seconds": r.get("setup_seconds"),
            "checks_seconds": r.get("checks_seconds"), "judge_seconds": r.get("judge_seconds"),
            "confined": r.get("confined"), "artifact_missing": r.get("artifact_missing", False),
            "final_message_excerpt": final[:REPORT_EXCERPT_CHARS]}


def report(out: Path, baseline: str | None = None, jobs: int = 6, strict_baseline: bool = False) -> dict:
    """One JSON document for a visualization agent: the plan a person can read at a glance (arms with their
    settings and instruction/artifact digests, scenarios with their prompts and judge questions, the
    decision rule when the plan states one), every run's record, per-arm and per-scenario aggregates with
    Wilson intervals, pairwise results, and baseline percentage differences. Data only: it draws no
    conclusion and renders nothing."""
    if not (out / "plan.json").exists():
        raise TrialError(f"{out} has no plan.json; name a directory that `trial.py run` wrote")
    plan = _stored_plan(out)
    loaded, _ = _load_results(out)
    results = [r for _, r in loaded]
    if not results:
        raise TrialError(f"no results under {out / 'runs'}")
    specs = {s["name"]: s for s in plan.get("scenarios", [])}
    with cf.ThreadPoolExecutor(jobs) as pool:
        runs = list(pool.map(lambda item: _run_record(item[0], item[1], specs), loaded))
    arms = sorted({r["arm"] for r in results})
    scenarios = sorted({r["scenario"] for r in results})
    arm_stats = {}
    for a in arms:
        st = _arm_stats(results, a)
        st["interval"] = wilson(st["passed"], st["valid"])
        arm_stats[a] = st
    scenario_table = {}
    for s in scenarios:
        for a in arms:
            rs = [r for r in results if r["scenario"] == s and r["arm"] == a]
            ok = [r for r in rs if r["passed"] is not None]
            k = sum(1 for r in ok if r["passed"])
            scenario_table[f"{s}|{a}"] = {"scenario": s, "arm": a, "passed": k, "valid": len(ok), "runs": len(rs),
                                          "invalid": sorted({_invalid_reason(r) for r in rs if r["passed"] is None}),
                                          "interval": wilson(k, len(ok)), "checks": _check_rates(ok)}
    explicit_baseline = baseline
    baseline = baseline or plan.get("baseline")
    if baseline and baseline not in arm_stats:
        if strict_baseline and explicit_baseline:
            raise TrialError(f"--baseline {baseline!r} does not name a loaded arm; valid arms: " + ", ".join(arms))
        baseline = None
    arm_executor = _arm_executors(results)
    payload = {
        "name": plan.get("name"), "run_directory": str(out),
        "plan": {
            "arms": {n: _identity(a) for n, a in plan.get("arms", {}).items()},
            "scenarios": [{"name": s.get("name"), "prompt": s.get("prompt"), "followups": s.get("followups", []),
                          "judge": s.get("judge"), "judge_role": s.get("judge_role"), "required": s.get("required", []),
                          "artifact": s.get("artifact")} for s in plan.get("scenarios", [])],
            "judge": _identity(plan["judge"], JUDGE_FIELDS) if plan.get("judge") else None,
        },
        "runs": runs, "arms": arm_stats, "scenarios": scenario_table, "pairwise": _load_pairwise(out),
    }
    if plan.get("decision_rule"):
        payload["plan"]["decision_rule"] = plan["decision_rule"]
    if baseline:
        payload["baseline"] = baseline
        payload["pct_vs_baseline"] = {a: _pct_vs_baseline(results, scenarios, a, baseline, arm_executor)
                                      for a in arms if a != baseline}
    return payload


# ---------------------------------------------------------------- cli

def _json_arg(text: str, flag: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise TrialError(f"{flag} is not valid JSON: {exc.msg} at character {exc.pos}") from None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="trial.py", description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a plan")
    r.add_argument("plan", type=Path)
    r.add_argument("--out", type=Path, help=f"run directory (default under {DEFAULT_OUT})")
    r.add_argument("--jobs", type=int, default=6)
    r.add_argument("--repeats", type=int)
    r.add_argument("--only", help="comma-separated scenario names")
    r.add_argument("--arms", help="comma-separated arm names")
    r.add_argument("--retry-invalid", action="store_true", help="rerun jobs whose earlier result was invalid")
    r.add_argument("--sandbox", choices=["confined", "none"],
                   help="default confinement for scenarios that name none of their own (default: confined; the "
                        "plan's own \"sandbox\" is used absent this flag). Without bubblewrap, a \"confined\" "
                        "scenario refuses to start rather than running unconfined; pass --sandbox none (or set "
                        "plan \"sandbox\": \"none\") to run unconfined explicitly")
    r.add_argument("--dry-run", action="store_true",
                   help="print the models and schedule and exit; asks no endpoint, so a latest: spec the run directory "
                        "has not resolved (and TRIAL_MODELS_FILE cannot answer) shows unresolved")
    d = sub.add_parser("derive", help="write a plan whose arms are artifacts that an earlier run produced")
    d.add_argument("out", type=Path, help="the earlier run directory")
    d.add_argument("--scenario", required=True, help="scenario in the earlier run whose runs produced the artifact")
    d.add_argument("--artifact", required=True, help="path of the artifact inside each run's working directory")
    d.add_argument("--consumer", required=True, type=Path, help="scenario directory the derived arms run")
    d.add_argument("--executor", default="{}",
                   help="base arm as JSON, merged over what each artifact's own source run recorded (default: {}), "
                        'e.g. {"model": "claude-sonnet-5-5"} to keep the source executor but pick a model, or '
                        '{"executor": "claude", "model": "...", "base_url": "..."} to replace it outright; a '
                        "codex or claude arm left with no model this way (an older run recorded none, and "
                        "--executor names none either) is an error")
    d.add_argument("--repeats", type=int, default=2)
    d.add_argument("--plan", required=True, type=Path, help="where to write the derived plan (its arms directory sits beside it)")
    c = sub.add_parser("recheck", help="recompute checks for finished runs after a check changes (no new agent runs)")
    c.add_argument("out", type=Path)
    c.add_argument("--rejudge", action="store_true",
                   help="also rerun the judge with each scenario's current question and evidence")
    c.add_argument("--judge", help="judge as JSON; it re-judges every run the judge scores and becomes the run directory's "
                                   "judge in plan.json, so --only cannot limit it while scenarios outside --only have finished "
                                   'runs with a judge question, e.g. {"executor": "claude", "model": "latest:claude-sonnet-*", '
                                   '"base_url": "https://proxy.example"}')
    c.add_argument("--only", help="comma-separated scenario names to re-score")
    c.add_argument("--jobs", type=int, default=6)
    c.add_argument("--sandbox", choices=["confined", "none"],
                   help="override the directory's plan-level default sandbox for this and future rechecks "
                        "(a scenario's own \"sandbox\" still wins); see `trial.py run --help`")
    m = sub.add_parser("models", help="list model IDs an endpoint serves (the Codex model provider by default)")
    m.add_argument("--match", help="glob to filter, e.g. 'claude-sonnet-*'; with --latest each * stands for a version number")
    m.add_argument("--latest", action="store_true", help="print only what latest:MATCH resolves to")
    m.add_argument("--base-url", help="an Anthropic-compatible endpoint to ask instead of the Codex provider (with the "
                                      "Codex provider's key unless --env-file or --api-key-var name another)")
    m.add_argument("--env-file", help="file holding the key (default: TRIAL_ENV_FILE, or none - then the key "
                                      "variable is read from this process's own environment)")
    m.add_argument("--api-key-var", help="variable in the env file holding the key (default: the Codex provider's env_key, "
                                         "or CODEX_API_KEY absent that; ANTHROPIC_API_KEY for --base-url)")
    s = sub.add_parser("summarize", help="summarize a run directory")
    s.add_argument("out", type=Path)
    s.add_argument("--json", action="store_true")
    s.add_argument("--group", action="store_true", help="pool derived arms by their source arm (the part before '~')")
    s.add_argument("--baseline", help="arm other arms' cost and timing show a percentage difference from "
                                      "(default: the plan's own \"baseline\", if it named one)")
    p = sub.add_parser("pairwise", help="blind pairwise judging of two arms' matched runs, in both presentation orders")
    p.add_argument("out", type=Path)
    p.add_argument("--arms", help="two comma-separated arm names to compare (default: the plan's own "
                                  "\"pairwise\": {\"arms\": [\"A\", \"B\"]})")
    p.add_argument("--judge-model", help="model for the pairwise judge, keeping the run directory's judge "
                                        "executor and other settings (default: that judge as recorded)")
    p.add_argument("--jobs", type=int, default=6)
    rp = sub.add_parser("report", help="write one JSON document (plan, runs, aggregates, pairwise) for a visualization agent")
    rp.add_argument("out", type=Path)
    rp.add_argument("--out", dest="report_file", type=Path, help="write the JSON here instead of stdout")
    rp.add_argument("--baseline", help="arm the percentage differences compare against "
                                       "(default: the plan's own \"baseline\", if it named one)")
    a = ap.parse_args(argv)
    try:
        if os.name != "posix":  # locking, timeouts, and every executor's shell step assume a POSIX host
            raise TrialError("native Windows is not supported; run this under WSL (Windows Subsystem for Linux)")
        if a.cmd == "summarize":
            baseline = a.baseline or _stored_plan(a.out).get("baseline")
            print(summarize(a.out, a.json, a.group, baseline, strict_baseline=bool(a.baseline)))
            return 0
        if a.cmd == "pairwise":
            plan = _stored_plan(a.out.resolve())
            arms = a.arms.split(",") if a.arms else plan.get("pairwise", {}).get("arms")
            if not arms or len(arms) != 2:
                raise TrialError("pairwise needs --arms A,B, or a plan \"pairwise\": {\"arms\": [\"A\", \"B\"]} block")
            base_judge = plan.get("judge")
            if not base_judge:
                raise TrialError(f"{a.out} has no judge in its plan.json; pairwise needs one (its executor "
                                 "and settings), optionally with --judge-model naming a different model")
            judge = _check_env_file(_check_judge(dict(base_judge, model=a.judge_model) if a.judge_model else base_judge,
                                                 "judge"), "judge")
            print(_pairwise_report(pairwise(a.out.resolve(), arms[0], arms[1], judge, a.jobs)))
            return 0
        if a.cmd == "report":
            payload = report(a.out.resolve(), a.baseline, strict_baseline=bool(a.baseline))
            text = _dumps_finite(payload, "report")
            if a.report_file:
                a.report_file.write_text(text + "\n")
                print(f"wrote {a.report_file}")
            else:
                print(text)
            return 0
        if a.cmd == "models":
            arm = {k: v for k, v in (("env_file", a.env_file), ("api_key_var", a.api_key_var)) if v}
            if a.base_url:
                arm.update(executor="claude", base_url=a.base_url)
            if a.latest and not a.match:
                raise TrialError("--latest needs --match, e.g. --match 'claude-sonnet-*'")
            ids = available_models(arm, "models")
            if a.latest:
                flags = "".join(f" --{k.replace('_', '-')} {shlex.quote(v)}"
                                for k, v in (("base_url", a.base_url), ("env_file", a.env_file), ("api_key_var", a.api_key_var)) if v)
                print(latest_model(a.match, ids, "models", flags))
            else:
                print("\n".join(sorted(i for i in ids if not a.match or fnmatch.fnmatch(i, a.match))))
            return 0
        if a.cmd == "derive":
            base = _json_arg(a.executor, "--executor")
            if not isinstance(base, dict):
                raise TrialError("--executor must be a JSON object, e.g. {\"model\": \"your-model-id\"}")
            n = derive(a.out, a.scenario, a.artifact, a.consumer, base, a.repeats, a.plan)
            print(f"wrote {a.plan} with {n} derived arms")
            return 0
        if a.cmd == "recheck":
            judge = _check_judge(_json_arg(a.judge, "--judge"), "--judge") if a.judge is not None else None
            print(f"rechecked {recheck(a.out, a.rejudge, a.jobs, judge, a.only.split(',') if a.only else None, a.sandbox)} runs")
            print(summarize(a.out, baseline=_stored_plan(a.out).get("baseline")))
            return 0
        only, arms = (a.only.split(",") if a.only else None), (a.arms.split(",") if a.arms else None)
        out = a.out.resolve() if a.out else None
        # Validate the plan, and resolve its models, before any directory exists; a dry run asks no endpoint.
        plan = load_plan(a.plan.resolve(), a.repeats, only, arms, _stored_plan(out) if out else {}, query=not a.dry_run)
        if a.sandbox:
            plan["sandbox"] = a.sandbox
        if a.dry_run:
            if out:
                _merge_stored_plan(out, plan)  # refuses what can be decided without an endpoint; writes nothing
            recorded = {}
            for _, r in _load_results(out)[0] if out else []:
                for key, record in ((r.get("arm"), r.get("identity")), ("", r.get("judge_identity"))):
                    if (record or {}).get("model"):
                        recorded.setdefault(key, record["model"])

            def shown(name, arm):
                model = arm.get("model", "-")
                if not model.startswith("latest:"):
                    return model
                if recorded.get(name):
                    return (f"{model} (resolved when the run starts; {out} holds these runs with {recorded[name]}, so the "
                            "run is refused unless it resolves to that)")
                return model + " (resolved when the run starts)"
            for name, arm in plan["arms"].items():
                print(f"arm\t{name}\t{arm.get('executor')}\t{shown(name, arm)}")
            if plan.get("judge"):
                print(f"judge\t{plan['judge'].get('executor')}\t{shown('', plan['judge'])}")
            for arm, spec, rep in schedule(plan):
                print(f"{spec['name']}\t{arm}\tr{rep}")
            return 0
        out = out or (DEFAULT_OUT / f"{plan['name']}-{dt.datetime.now():%Y%m%d-%H%M%S}").resolve()
        if any((p / ".git").exists() for p in [out, *out.parents]):
            raise TrialError(f"{out} is inside a git repository; choose --out outside any repository")
        if _needs_bwrap(plan) and not shutil.which("bwrap"):
            # Refused here, before the run directory or plan.json exists and before any scenario's setup.sh
            # has run: the same check inside confine_prefix would otherwise only fire per job, once that
            # job's own executor or check actually needed confinement, after every earlier job in the batch
            # had already run its own setup.sh and left a ".pending" marker behind.
            raise TrialError("confined runs need bubblewrap (bwrap); install it, or pass --sandbox none "
                             "(or plan/scenario \"sandbox\": \"none\") to run unconfined")
        out.mkdir(parents=True, exist_ok=True)
        with _lock(out):
            plan = load_plan(a.plan.resolve(), a.repeats, only, arms, _stored_plan(out))
            if a.sandbox:
                plan["sandbox"] = a.sandbox
            _preflight_binaries(plan)
            _snapshot_instructions(plan, out)
            _snapshot_artifacts(plan, out)
            jobs = schedule(plan)
            _write_json(out / "plan.json", _merge_stored_plan(out, plan))
            print(f"run directory: {out}", flush=True)
            with cf.ThreadPoolExecutor(a.jobs) as pool:
                for res in pool.map(lambda j: run_job(plan, out, j, a.retry_invalid), jobs):
                    print(f"{res['job']}\t{res['status']}\tpassed={res['passed']}", flush=True)
            summary = summarize(out, baseline=plan.get("baseline"))
            (out / "summary.md").write_text(summary + "\n")
        print(summary)
        return 0
    except TrialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
