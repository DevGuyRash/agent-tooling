#!/usr/bin/env python3
"""Run repeated, isolated, interleaved trials of alternatives and summarize them.

A plan names arms (the alternatives: an executor plus its model and instructions) and
scenarios (a task with an optional fixture, fake tools, and checks). Every arm runs every
scenario `repeats` times, each run in its own fresh home and working directory, in an
interleaved order. Each run keeps its native record (events, final message, the executor's
session files) and a result with deterministic check outcomes and an optional blind judge
verdict. Summaries report per-scenario pass counts with 95% Wilson intervals.

    trial.py run PLAN.json [--out DIR] [--jobs N] [--repeats K] [--only A,B] [--arms A,B] [--retry-invalid]
    trial.py recheck DIR [--rejudge] [--judge JSON]  (re-score finished runs after a check or judge question changes)
    trial.py derive DIR --scenario S --artifact PATH --consumer SCENARIO_DIR --plan PLAN.json
                                  (second stage: artifacts from an earlier run become arms)
    trial.py summarize DIR [--json]
    trial.py models [--match GLOB] [--latest] [--base-url URL] [--env-file F] [--api-key-var V]
                                  (model IDs an endpoint serves)

Plan (paths relative to the plan file):

    {"name": "kernel-screen", "repeats": 5, "seed": 1,
     "arms": {"none":   {"executor": "codex", "model": "${TRIAL_CODEX_MODEL:-latest:gpt-*-luna}", "effort": "high"},
              "kernel": {"executor": "codex", "model": "${TRIAL_CODEX_MODEL:-latest:gpt-*-luna}", "effort": "high",
                         "instructions": "arms/kernel.md"}},
     "scenarios": ["../scenarios/blocked-deploy"],
     "judge": {"executor": "codex", "model": "gpt-6-luna", "effort": "high"}}

Settings fields (model, effort, base_url, binary, env_file, api_key_var) expand ${VAR} and
${VAR:-default}; a model "latest:GLOB" resolves to the newest numeric version the endpoint serves,
once per run directory: a rerun into the directory reuses the model it recorded for that spec. Every
run records its arm's model settings and instructions digest (executors read a copy of the
instructions kept in the run directory) and the judge that scored it, and a rerun that would mix
them in one directory is refused.

Scenario directory:

    scenario.json  {"prompt": "...", "followups": ["..."], "timeout_s": 900,
                    "sandbox": "confined", "required": ["check_name", ...],
                    "judge": {"question": "...", "pass_when": "..."}}
    fixture/       copied into the working directory
    setup.sh       optional; runs in the working directory before the agent starts
    bin/           optional fake tools, prepended to PATH (scenario.json "bin" can list other
                   directories relative to the scenario); tools may append JSON lines to
                   "$TRIAL_HARNESS/calls.jsonl"
    check.py       def check(run) -> {name: bool | number | str}
                   optional def judge_context(run) -> str (evidence shown to the judge)

Executors: "codex" (codex exec in a private CODEX_HOME holding only the model provider
settings plus the arm's instructions as AGENTS.md), "claude" (claude -p --bare with the
arm's instructions appended to the system prompt), and "command" (a shell command, for
non-agent comparisons and for testing this runner). Runs live outside any git repository
so executors cannot discover unrelated project instructions. By default ("sandbox":
"confined") codex and command runs execute inside bubblewrap with the host read-only, the
user's home hidden, and only the run directory writable; their environment reaches only the
scenario's tools and throwaway HOME, git, and gh configuration.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import contextlib
import datetime as dt
import errno
import fcntl
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
import stat
import subprocess
import sys
import tempfile
import threading
import tomllib
import urllib.parse
from pathlib import Path

DEFAULT_OUT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "agent-trials"
CODEX_HOME_SRC = Path(os.environ.get("TRIAL_CODEX_SOURCE_HOME", Path.home() / ".codex"))


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
        selected[name] = _with_instructions(_check_env_file(resolve_arm(arm, f"arm '{name}'", stored, query, base), f"arm '{name}'"),
                                            base, f"arm '{name}'")
    if not selected:
        raise TrialError("no arms selected; valid arms: " + ", ".join(plan["arms"]))
    plan["arms"] = selected
    plan["scenarios"] = scenarios
    if plan.get("judge") is not None:
        plan["judge"] = _check_env_file(resolve_arm(_check_judge(plan["judge"], "judge"), "judge", stored, query, base), "judge")
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
                         f"5-5 or 6.1 (name a family by its suffix, as in latest:gpt-*-luna); list the candidates with "
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


def available_models(arm: dict, where: str = "models") -> list[str]:
    """Model IDs the arm's endpoint serves: a Claude arm asks its base_url (Anthropic format), any other arm
    asks the Codex model provider (OpenAI format). The key (api_key_var in env_file, by default the Codex
    provider's) is read by a child process only. TRIAL_MODELS_FILE (one ID per line) replaces the query."""
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
                             "TRIAL_MODELS_FILE (or pass --base-url to `trial.py models`), or name an exact model (derived "
                             "plans read TRIAL_CODEX_MODEL)")
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
    if arm.get("env_file") and not Path(arm["env_file"]).expanduser().exists():
        raise TrialError(f"{where}: env_file {arm['env_file']} does not exist")
    env_file = Path(arm.get("env_file", CODEX_HOME_SRC / "codex.env")).expanduser().resolve()
    var = arm.get("api_key_var") or _provider_key_var()
    cache = (url, str(env_file), var)
    if cache not in _MODELS:
        prefix = _key_prefix(env_file, var, "TRIAL_MODELS_KEY") if var else []
        try:
            r = subprocess.run(prefix + [sys.executable, "-I", "-c", _LIST_MODELS, url, "anthropic" if anthropic else "openai",
                                         "key" if prefix else "none"],
                               env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                                    **{k: v for k, v in os.environ.items() if k in _NET_ENV}},
                               capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            raise TrialError(f"timed out listing models from {shown}") from None
        if r.returncode != 0:
            reason = (r.stderr.strip().splitlines() or ["no response"])[-1]
            if reason == "NO_KEY":
                reason = f"{var} is unset or empty in {env_file}"
            elif reason == "BAD_KEY":
                reason = (f"{var} in {env_file} holds a line break or a non-ASCII character (a CRLF line ending or a pasted "
                          "quote?), which a request header cannot carry")
            elif reason in ("HTTP 401", "HTTP 403") and not prefix and var:
                reason += f" (no key was sent: {env_file} does not exist; set env_file, or --env-file for `trial.py models`)"
            elif reason in ("HTTP 401", "HTTP 403") and not prefix:
                reason += " (no key was sent; name one with api_key_var and env_file, or give the Codex provider an env_key)"
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
IDENTITY_FIELDS = ("executor", "model", "effort", "base_url", "instructions_sha256", "command", "allowed_tools",
                   "permission_mode")
JUDGE_FIELDS = IDENTITY_FIELDS[:4]


def _effective(ident: dict, judge: bool) -> dict:
    """A recorded identity with the defaults the executors apply, so writing out a default is no change."""
    ident = {k: v for k, v in ident.items() if v not in (None, "", [])}
    if ident.get("executor") == "codex":
        ident.setdefault("effort", "high" if judge else "medium")
    if ident.get("executor") != "claude":
        ident.pop("allowed_tools", None)
        ident.pop("permission_mode", None)
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


def _stored_plan(out: Path) -> dict:
    path = out / "plan.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise TrialError(f"cannot read {path}: {exc}") from None


@contextlib.contextmanager
def _lock(out: Path):
    """One run or recheck per run directory at a time: another would replace the first one's jobs and records."""
    fd = os.open(out / ".trial.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise TrialError(f"{out} is in use by another trial.py run or recheck; wait for it or use a new --out") from None
        yield
    finally:
        os.close(fd)


def _refuse_changes(what: str, entry: dict, runs: list[dict], field: str, stored_entry: dict | None, out: Path, hint: str,
                    fields=IDENTITY_FIELDS):
    """Refuse `entry` when its settings differ from what `runs` recorded in `field` (plan.json for older runs)."""
    if not runs:
        return
    records = [(r[field], fields) for r in runs if field in r]
    if len(records) < len(runs):
        if not stored_entry:
            raise TrialError(f"{out} holds runs of {what} with no record of their settings; use a new --out")
        records.append((_identity(stored_entry, IDENTITY_FIELDS[:4]), IDENTITY_FIELDS[:4]))
    judge = fields is JUDGE_FIELDS
    now = _effective(_identity(entry, fields), judge)
    unresolved = str(now.get("model", "")).startswith("latest:")  # a dry run that asked no endpoint
    for record, fields in records:
        record = _effective(record, judge)
        diffs = []
        for k in fields:
            if record.get(k) == now.get(k) or (k == "model" and unresolved):
                continue
            if k in ("instructions_sha256", "command"):
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
    for name, arm in plan["arms"].items():
        _refuse_changes(f"arm '{name}'", arm, [r for r in results if r.get("arm") == name], "identity",
                        stored.get("arms", {}).get(name), out, "restore them or use a new --out")
    specs = {**{sp["name"]: _current(sp) for sp in stored.get("scenarios", [])}, **{sp["name"]: sp for sp in plan["scenarios"]}}
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

def _provider_config(model: str, effort: str) -> str:
    """Minimal Codex config: the user's model provider, nothing that loads instructions."""
    lines = [f'model = "{model}"', f'model_reasoning_effort = "{effort}"',
             'model_reasoning_summary = "detailed"', 'web_search = "disabled"',
             # no plugin catalog, apps, or memories: each would load outside the arm and cost disk per run
             "[features]", "plugins = false", "remote_plugin = false", "apps = false", "memories = false", ""]
    src = CODEX_HOME_SRC / "config.toml"
    if src.exists():
        cfg = tomllib.loads(src.read_text())
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
        if exc.errno not in (errno.ELOOP, errno.ENXIO, errno.EISDIR):
            raise
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


def confine_prefix(job_dir: Path, readable: list[Path], *, network=True, writable=True, chdir: Path | None = None) -> list[str]:
    """Wrap a command in bubblewrap: the host is read-only, the user's home is hidden, the command and
    everything it starts live in their own process namespace and end with it, and only the run
    directory is writable. Network stays available for model APIs unless network is False."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise TrialError("confined runs need bubblewrap (bwrap); install it or set \"sandbox\" explicitly")
    cmd = [bwrap, "--ro-bind", "/", "/", "--tmpfs", str(Path.home()), "--dev", "/dev", "--proc", "/proc",
           "--tmpfs", "/tmp", "--unshare-pid", "--die-with-parent"] + ([] if network else ["--unshare-net"])
    for path in readable:
        if path.exists():
            cmd += ["--ro-bind", str(path), str(path)]
    return cmd + ["--bind" if writable else "--ro-bind", str(job_dir), str(job_dir),
                  "--chdir", str(chdir or job_dir / "work"), "--"]


def _codex_sandbox(spec):
    """'confined' (default) runs Codex unsandboxed inside bubblewrap so agents can commit;
    any other value is passed to Codex's own sandbox."""
    mode = spec.get("sandbox", "confined")
    return ("danger-full-access", True) if mode == "confined" else (mode, False)


def _codex_readable(codex: str) -> list[Path]:
    install = Path(codex).resolve().parents[3] if Path(codex).exists() else Path(codex).parent
    return [install, Path(codex).parent]


def run_codex(arm, spec, job_dir: Path, env):
    home = job_dir / "home"
    home.mkdir()
    (home / "config.toml").write_text(_provider_config(arm["model"], arm.get("effort", "medium")))
    cache = CODEX_HOME_SRC / "models_cache.json"
    if cache.exists():
        shutil.copy(cache, home / "models_cache.json")
    if arm.get("instructions"):
        shutil.copy(arm["instructions"], home / "AGENTS.md")
    env = dict(env, CODEX_HOME=str(home))
    env_file = Path(arm.get("env_file", CODEX_HOME_SRC / "codex.env"))
    prefix = _key_prefix(env_file, arm.get("api_key_var") or _provider_key_var())
    codex = arm.get("binary") or shutil.which("codex", path=str(Path.home() / ".npm-global/bin")) or "codex"
    sandbox, confined = _codex_sandbox(spec)
    if confined:  # the key is exported outside, then bwrap inherits it; the credential file stays hidden
        prefix = prefix + confine_prefix(job_dir, [*_codex_readable(codex),
                                                   *[Path(p).expanduser() for p in arm.get("readable", [])]])
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
        thread = thread or _thread_id(job_dir / "events.jsonl")
        if timed_out:
            status = "timeout"
            break
        if code != 0:
            status = f"exit-{code}"
            break
    return status


def _provider_block() -> dict:
    """The Codex config's model provider settings (base_url, env_key, ...), or {}."""
    src = CODEX_HOME_SRC / "config.toml"
    if not src.exists():
        return {}
    cfg = tomllib.loads(src.read_text())
    return cfg.get("model_providers", {}).get(cfg.get("model_provider") or "", {})


def _provider_key_var():
    """Name of the environment variable holding the Codex model provider's key (read from config, never its value)."""
    return _provider_block().get("env_key")


def _claude_binary(arm):
    return arm.get("binary") or ("/opt/claude-code/bin/claude" if Path("/opt/claude-code/bin/claude").exists()
                                 else shutil.which("claude") or "claude")


def _claude_proxy(arm, env):
    """With "base_url", point Claude Code at that endpoint and load its key into the child only."""
    if not arm.get("base_url"):
        return env, []
    env_file = Path(arm.get("env_file", CODEX_HOME_SRC / "codex.env"))
    var = arm.get("api_key_var") or _provider_key_var()
    if not var or not env_file.exists():
        raise TrialError("claude arm with base_url needs api_key_var and env_file (or a Codex provider config)")
    # The key moves from the env file into ANTHROPIC_API_KEY inside the child only; nothing here reads it.
    return dict(env, ANTHROPIC_BASE_URL=arm["base_url"]), _key_prefix(env_file, var, "ANTHROPIC_API_KEY")


def run_claude(arm, spec, job_dir: Path, env):
    """Claude Code in bare mode: no hooks, plugins, memory, or CLAUDE.md discovery.

    With "base_url" (an Anthropic-compatible endpoint such as a model proxy) the key comes from
    "api_key_var" (default: the Codex provider's key variable) in the env file, the run is confined
    like codex runs, and HOME is the run's own; without it, ANTHROPIC_API_KEY must already be set."""
    binary = _claude_binary(arm)
    confined = spec.get("sandbox", "confined") == "confined"
    cmd = [binary, "-p", "--bare", "--output-format", "stream-json", "--verbose", "--model", arm["model"],
           "--permission-mode", arm.get("permission_mode", "bypassPermissions" if confined else "acceptEdits"),
           "--add-dir", str(job_dir / "harness")]
    if arm.get("effort"):
        cmd += ["--effort", arm["effort"]]
    if arm.get("instructions"):
        cmd += ["--append-system-prompt-file", arm["instructions"]]
    if arm.get("allowed_tools"):
        cmd += ["--allowed-tools", *arm["allowed_tools"]]
    env, prefix = _claude_proxy(arm, env)
    if confined:
        readable = [Path(binary).resolve().parent, *([Path(arm["instructions"])] if arm.get("instructions") else [])]
        prefix = prefix + confine_prefix(job_dir, readable)  # the key is loaded outside, then bwrap inherits it
    timeout = spec.get("timeout_s", 900)
    for i, prompt in enumerate([spec["prompt"], *spec.get("followups", [])]):
        c = prefix + cmd + (["--continue"] if i else [])
        before = len(_read(job_dir / "events.jsonl", follow=False).splitlines())
        code, timed_out = _run(c, cwd=job_dir / "work", env=env, stdin_text=prompt, timeout=timeout,
                               stdout_path=job_dir / "events.jsonl", stderr_path=job_dir / "stderr.log")
        for line in _read(job_dir / "events.jsonl", follow=False).splitlines()[before:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "result" and isinstance(event.get("result"), str):
                _write_atomic(job_dir / f"final-{i}.md", event["result"].encode())
        if timed_out:
            return "timeout"
        if code != 0:
            return f"exit-{code}"
    return "ok"


def run_command(arm, spec, job_dir: Path, env):
    prompt = spec["prompt"]
    prefix = []
    instructions = arm.get("instructions") or ""
    if spec.get("sandbox", "confined") == "confined" and arm.get("confine", True) and shutil.which("bwrap"):
        prefix = confine_prefix(job_dir, [Path(spec["dir"]), *([Path(instructions)] if instructions else [])])
    code, timed_out = _run(prefix + ["sh", "-c", arm["command"]], cwd=job_dir / "work",
                           env=dict(env, TRIAL_PROMPT=prompt, TRIAL_SCENARIO_DIR=spec["dir"],
                                    TRIAL_JOB_DIR=str(job_dir), TRIAL_INSTRUCTIONS=instructions), stdin_text=prompt,
                           timeout=spec.get("timeout_s", 300), stdout_path=job_dir / "events.jsonl",
                           stderr_path=job_dir / "stderr.log")
    return "timeout" if timed_out else ("ok" if code == 0 else f"exit-{code}")


EXECUTORS = {"codex": run_codex, "claude": run_claude, "command": run_command}


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
    return skip


GIT_HARDENING = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "diff.external=",
                 "-c", "core.pager=cat", "-c", "protocol.allow=never", "-c", "core.sshCommand=false",
                 "-c", "credential.helper=", "-c", "gpg.program=false", "-c", "core.alternateRefsCommand=false"]
GIT_ENV = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}


class Run:
    """What a check sees: the resulting state and the native record of one run."""

    def __init__(self, job_dir: Path, status: str):
        self.dir = job_dir
        self.workdir = job_dir / "work"
        self.harness = job_dir / "harness"
        self.status = status
        self.events = []
        for line in self.read(job_dir / "events.jsonl").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):  # a command arm may print JSON scalars or lists
                self.events.append(event)
        self.messages = [t for t in (_message_text(e) for e in self.events) if t]
        finals = sorted(job_dir.glob("final-*.md"))
        self.final_message = self.read(finals[-1]) if finals else (self.messages[-1] if self.messages else "")
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
        settings are overridden, and git runs confined (read-only, no network) where bubblewrap exists."""
        cmd = ["git", *GIT_HARDENING, *args]
        cwd = Path(cwd or self.workdir)
        if shutil.which("bwrap") and cwd.exists():
            cmd = confine_prefix(self.dir, [], network=False, writable=False, chdir=cwd) + cmd
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
        hidden, its own process namespace, and only `cwd` writable. Returns the completed process, or None
        when it timed out."""
        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise TrialError("checks that run agent code need bubblewrap (bwrap)")
        cwd = Path(cwd or self.workdir)
        prefix = [bwrap, "--ro-bind", "/", "/", "--tmpfs", str(Path.home()), "--dev", "/dev", "--proc", "/proc",
                  "--tmpfs", "/tmp", "--unshare-pid", "--unshare-net", "--die-with-parent",
                  "--bind", str(cwd), str(cwd), "--chdir", str(cwd), "--"]
        base = {"PATH": "/usr/bin:/bin", "HOME": str(cwd), "TMPDIR": str(cwd), "LANG": "C.UTF-8",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            return subprocess.run(prefix + list(cmd), cwd=cwd, env=dict(base, **(env or {})),
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None


def _write_json(path: Path, obj):
    _write_atomic(path, json.dumps(obj, indent=1).encode())


def _write_atomic(path: Path, data: bytes):
    """Write through a private temporary file, so a reader never sees a partial file."""
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
        try:
            results.append((p, json.loads(p.read_text())))
        except (OSError, json.JSONDecodeError):
            skipped += 1
    return results, skipped


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
            data = f.read()
    except OSError:
        return ""
    finally:
        os.close(fd)
    return data.decode(errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _message_text(e):
    item = e.get("item") if isinstance(e, dict) else None
    if e.get("type") == "item.completed" and item and item.get("type") == "agent_message":
        return item.get("text", "")
    if e.get("type") == "assistant":  # claude stream-json
        return "".join(b.get("text", "") for b in e.get("message", {}).get("content", [])
                       if isinstance(b, dict) and b.get("type") == "text")
    return None


def _command_text(e):
    item = e.get("item") if isinstance(e, dict) else None
    if e.get("type") == "item.completed" and item and item.get("type") == "command_execution":
        return item.get("command", "")
    if e.get("type") == "assistant":
        for b in e.get("message", {}).get("content", []):
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                return b.get("input", {}).get("command", "")
    return None


def _usage(events):
    total = {}
    for e in events:
        u = e.get("usage") if e.get("type") in ("turn.completed", "result") else None
        for k, v in (u or {}).items():
            if isinstance(v, (int, float)):
                total[k] = total.get(k, 0) + v
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


JUDGE_SCHEMA = {"type": "object", "additionalProperties": False,
                "required": ["verdict", "reason"],
                "properties": {"verdict": {"type": "string", "enum": ["pass", "fail", "unclear"]},
                               "reason": {"type": "string"}}}


def _remove(path: Path):
    """Remove what is at path: a link or file is unlinked, never followed; a directory is removed with its contents."""
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _fresh_dir(path: Path) -> Path:
    """An empty directory at path, replacing whatever an agent left there."""
    _remove(path)
    path.mkdir()
    return path


def _judge_confinement(job_dir: Path, jd: Path, readable: list[Path]) -> list[str]:
    """The judge reads text an agent wrote, so it runs with the user's home hidden, like the agents."""
    return confine_prefix(job_dir, readable, chdir=jd / "work") if shutil.which("bwrap") else []


def judge_run(plan, spec, run: Run, checks_mod, job_dir: Path, env, name="judge"):
    """Blind verdict on one run, kept in job_dir/name: the judge sees the task and evidence, never the arm."""
    j = spec.get("judge")
    if not j or not plan.get("judge"):
        return None
    try:
        evidence = checks_mod.judge_context(run) if checks_mod and hasattr(checks_mod, "judge_context") else ""
    except Exception as exc:
        return {"verdict": "error", "reason": f"judge_context: {type(exc).__name__}: {exc}"}
    prompt = (
        "You are judging one run of an AI agent on a task. You see the task it was given, the agent's "
        "final message, and evidence about the resulting state. Judge only the question below against "
        "this evidence.\n\n<task>\n" + spec["prompt"] + "\n</task>\n\n"
        + "".join(f"<followup>\n{f}\n</followup>\n\n" for f in spec.get("followups", []))
        + "<final_message>\n" + run.final_message.strip() + "\n</final_message>\n\n"
        + ("<evidence>\n" + evidence.strip() + "\n</evidence>\n\n" if evidence else "")
        + "<question>\n" + j["question"] + "\n</question>\n\n"
        + "verdict is 'pass' when " + j["pass_when"] + "; 'fail' when it clearly does not; 'unclear' "
        "only when the evidence cannot decide. reason is one sentence of at most 40 words."
    )
    jd = _fresh_dir(job_dir / name)
    (jd / "work").mkdir()
    (jd / "harness").mkdir()
    (jd / "prompt.md").write_text(prompt)
    jarm = dict(plan["judge"])
    if jarm["executor"] == "codex":
        schema = jd / "schema.json"
        schema.write_text(json.dumps(JUDGE_SCHEMA))
        home = jd / "home"
        home.mkdir()
        (home / "config.toml").write_text(_provider_config(jarm["model"], jarm.get("effort", "high")))
        cache = CODEX_HOME_SRC / "models_cache.json"
        if cache.exists():
            shutil.copy(cache, home / "models_cache.json")
        codex = jarm.get("binary") or shutil.which("codex", path=str(Path.home() / ".npm-global/bin")) or "codex"
        cmd = _key_prefix(Path(jarm.get("env_file", CODEX_HOME_SRC / "codex.env")),
                          jarm.get("api_key_var") or _provider_key_var()) + _judge_confinement(job_dir, jd, _codex_readable(codex)) + [
            codex, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-m", jarm["model"],
            "-c", f"model_reasoning_effort={jarm.get('effort', 'high')}", "-C", str(jd / "work"),
            "--output-schema", str(schema), "-o", str(jd / "verdict.json"), "-"]
        _run(cmd, cwd=jd / "work", env=dict(env, CODEX_HOME=str(home)), stdin_text=prompt,
             timeout=600, stdout_path=jd / "events.jsonl", stderr_path=jd / "stderr.log")
    elif jarm["executor"] == "claude":
        jenv, prefix = _claude_proxy(jarm, env)
        binary = _claude_binary(jarm)
        cmd = prefix + _judge_confinement(job_dir, jd, [Path(binary).resolve().parent]) + [binary, "-p", "--bare", "--model", jarm["model"],
                        "--output-format", "json", "--json-schema", json.dumps(JUDGE_SCHEMA)]
        if jarm.get("effort"):
            cmd += ["--effort", jarm["effort"]]
        _run(cmd, cwd=jd / "work", env=jenv, stdin_text=prompt, timeout=600,
             stdout_path=jd / "verdict.raw.json", stderr_path=jd / "stderr.log")
        raw = _read(jd / "verdict.raw.json", follow=False)
        try:
            out = json.loads(raw)
            _write_atomic(jd / "verdict.json", json.dumps(out.get("structured_output") or json.loads(out["result"])).encode())
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            pass
    try:
        verdict = json.loads(_read(jd / "verdict.json", follow=False))
    except json.JSONDecodeError:
        verdict = None
    if not (isinstance(verdict, dict) and isinstance(verdict.get("verdict"), str)):
        return {"verdict": "error", "reason": "judge produced no verdict"}
    return verdict


# ---------------------------------------------------------------- environment

SYSTEM_PATH = ["/usr/bin", "/bin", "/usr/sbin", "/sbin"]
SCRUB = ("GIT_DIR", "GIT_WORK_TREE", "CODEX_HOME", "CLAUDECODE", "SSH_AUTH_SOCK", "GPG_AGENT_INFO",
         "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "ZDOTDIR", "BASH_ENV", "ENV")


def isolated_env(job_dir: Path, out: Path, spec, fake_home=True):
    """An environment that reaches only the scenario's tools and throwaway identities.

    Scenario tools are copied into the run so their location reveals nothing about the
    scenario's checks. PATH is rebuilt from system directories, so user-level wrappers and
    credentials are out of reach; HOME, git, and gh configuration are private to the run.
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
    env = {k: v for k, v in os.environ.items() if k not in SCRUB}
    harness = job_dir / "harness"
    env.update(TRIAL_HARNESS=str(harness), GIT_CEILING_DIRECTORIES=str(out), GIT_CONFIG_NOSYSTEM="1",
               GH_CONFIG_DIR=str(harness / ".gh"), PATH=os.pathsep.join([str(tools), *SYSTEM_PATH]),
               GIT_TERMINAL_PROMPT="0")
    gitconfig = harness / ".gitconfig"
    gitconfig.write_text("[user]\n\tname = Acme Dev\n\temail = dev@acme.example\n"
                         "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n"
                         "[tag]\n\tgpgsign = false\n")
    env["GIT_CONFIG_GLOBAL"] = str(gitconfig)
    if fake_home:
        home = harness / "home"
        home.mkdir(exist_ok=True)
        shutil.copy(gitconfig, home / ".gitconfig")
        env["HOME"] = str(home)
        env.pop("XDG_CONFIG_HOME", None)
        env.pop("XDG_CACHE_HOME", None)
    return env


# ---------------------------------------------------------------- one job

MIN_FREE_BYTES = int(os.environ.get("TRIAL_MIN_FREE_GB", "5")) * 1024 ** 3
PRUNE = ("home/.tmp", "home/skills", "home/models_cache.json", "judge/home/.tmp", "judge/home/skills",
         "judge/home/models_cache.json", "harness/home/.cache")


def _prune(job_dir: Path):
    """Remove per-run caches that hold no evidence (host plugin catalogs, bundled skill copies). A path through a
    link an agent planted is skipped, and a link in a cache's place is removed, never its target."""
    for rel in PRUNE:
        target = job_dir
        for part in Path(rel).parts[:-1]:
            target = target / part
            if target.is_symlink() or not target.is_dir():
                break
        else:
            target = target / Path(rel).name
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target, ignore_errors=True)


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
        stderr = _read(out / "runs" / result["job"] / "stderr.log")
        if result["status"] == "ok" or not any(t in stderr for t in TRANSPORT):
            return result
    return result


def _run_job_once(plan, out: Path, job, retry_invalid):
    arm_name, spec, rep = job
    arm = plan["arms"][arm_name]
    job_id = f"{spec['name']}__{arm_name}__r{rep}"
    job_dir = out / "runs" / job_id
    result_path = job_dir / "result.json"
    if result_path.exists():
        try:
            previous = json.loads(result_path.read_text())
        except (OSError, json.JSONDecodeError):
            previous = {"passed": None}  # an interrupted write: run the job again
            retry_invalid = True
        if not (retry_invalid and previous.get("passed") is None):
            return previous
    _check_space(out)
    if job_dir.exists():
        shutil.rmtree(job_dir)  # a partial earlier attempt; results are never mixed
    (job_dir / "work").mkdir(parents=True)
    (job_dir / "harness").mkdir()
    sdir = Path(spec["dir"])
    if (sdir / "fixture").is_dir():
        shutil.copytree(sdir / "fixture", job_dir / "work", dirs_exist_ok=True)
    env = isolated_env(job_dir, out, spec, fake_home=arm["executor"] != "claude" or bool(arm.get("base_url")))
    started = dt.datetime.now(dt.timezone.utc)
    if (sdir / "setup.sh").exists():
        r = subprocess.run(["sh", str(sdir / "setup.sh")], cwd=job_dir / "work", env=env,
                           capture_output=True, text=True, timeout=300)
        (job_dir / "setup.log").write_text(r.stdout + r.stderr)
        if r.returncode != 0:
            result = {"job": job_id, "arm": arm_name, "scenario": spec["name"], "repeat": rep,
                      "status": "setup-failed", "passed": None, "identity": _identity(arm)}
            _write_json(result_path, result)
            return result
    status = EXECUTORS[arm["executor"]](arm, spec, job_dir, env)
    run = Run(job_dir, status)
    checks_mod, checks = _checks_for(spec, run)
    verdict = judge_run(plan, spec, run, checks_mod, job_dir, env) if "check_error" not in checks else None
    required = spec.get("required", [])
    passed = None
    if status == "ok" and "check_error" not in checks:
        passed = all(checks.get(name) is True for name in required)
        if spec.get("judge") and plan.get("judge") and spec.get("judge_required", True):
            v = (verdict or {}).get("verdict")
            passed = None if v == "error" else passed and v == "pass"
    result = {"job": job_id, "arm": arm_name, "scenario": spec["name"], "repeat": rep, "status": status,
              "passed": passed, "checks": checks, "judge": verdict, "usage": run.usage,
              "commands": len(run.commands),
              "seconds": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 1),
              "identity": _identity(arm)}
    if verdict is not None:
        result["judge_identity"] = _identity(plan["judge"], JUDGE_FIELDS)
    _write_json(result_path, result)
    _prune(job_dir)
    return result


def derive(out: Path, scenario: str, artifact: str, consumer: Path, base: dict, repeats: int, plan_path: Path) -> int:
    """A second-stage plan: each artifact an earlier run produced becomes an arm's instructions.

    Arm names are '<source arm>~r<repeat>', so `summarize --group` pools each source arm's artifacts."""
    base = dict(base or {"executor": "codex", "model": "${TRIAL_CODEX_MODEL:-latest:gpt-*-luna}", "effort": "high"})
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
        target = arms_dir / f"{name.replace('~', '__')}.md"
        shutil.copy(produced, target)
        arms[name] = dict(base, instructions=str(target.relative_to(plan_path.parent)))
    if not arms:
        raise TrialError(f"no finished '{scenario}' runs with {artifact} under {out / 'runs'}")
    plan = {"name": plan_path.stem, "repeats": repeats, "seed": 1, "arms": arms,
            "scenarios": [os.path.relpath(consumer.resolve(), plan_path.parent.resolve())]}
    plan_path.write_text(json.dumps(plan, indent=1))
    return len(arms)


def recheck(out: Path, rejudge=False, jobs=6, judge=None, only=None) -> int:
    """Re-score finished runs with the scenarios' current checks, and optionally their current judge.

    Without rejudge, stored judge verdicts are kept. With it, the judge runs again on the stored run
    (its final message and resulting state) using the scenario's current question and evidence.
    `judge` becomes the run directory's judge: it implies rejudge and re-judges every run the judge scores,
    so it refuses before judging anything when one of them cannot be re-judged."""
    if not (out / "plan.json").exists():
        raise TrialError(f"{out} has no plan.json; name a directory that `trial.py run` wrote")
    with _lock(out):
        plan = _stored_plan(out)
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
            return path, result, spec, _checks_for(spec, Run(path.parent, result["status"]))[1]

        with cf.ThreadPoolExecutor(jobs) as pool:
            scored = [x for x in pool.map(score, loaded) if x]
        broken = sorted(r["job"] for _, r, spec, checks in scored
                        if judge is not None and r["status"] == "ok" and spec.get("judge") and "check_error" in checks)
        if broken:
            raise TrialError(f"--judge re-judges every run, but the checks of {', '.join(broken[:5])}"
                             f"{' and others' if len(broken) > 5 else ''} fail to run; fix them (a plain `trial.py recheck` "
                             "shows the errors), or use a new --out")

        def judge_one(item):
            """A new verdict in judge.next/; the stored judge/ stays until every verdict is in."""
            path, result, spec, checks = item
            if not (rejudge and result["status"] == "ok" and spec.get("judge") and plan.get("judge") and "check_error" not in checks):
                return None
            # The agent's harness and tools directories may be links it planted; the judge needs neither.
            env_dir = Path(tempfile.mkdtemp(prefix="judge-env-", dir=path.parent))
            (env_dir / "harness").mkdir()
            try:
                return judge_run(plan, spec, Run(path.parent, result["status"]), _load_checks(spec), path.parent,
                                 isolated_env(env_dir, out, spec), "judge.next")
            finally:
                shutil.rmtree(env_dir, ignore_errors=True)

        try:
            with cf.ThreadPoolExecutor(jobs) as pool:
                verdicts = list(pool.map(judge_one, scored))
            failed = [item[1]["job"] for item, v in zip(scored, verdicts) if v and v.get("verdict") == "error"]
            if judge is not None and failed:
                raise TrialError(f"the new judge produced no verdict for {', '.join(failed[:5])}"
                                 f"{' and others' if len(failed) > 5 else ''} (see judge.next/ in a run while it runs, or "
                                 "the judge's stderr); nothing was changed")
        except BaseException:
            for path, *_ in scored:
                _remove(path.parent / "judge.next")
            raise

        def finish(item, verdict):
            path, result, spec, checks = item
            if verdict is not None:
                _remove(path.parent / "judge")
                os.replace(path.parent / "judge.next", path.parent / "judge")
                result["judge"] = dict(verdict, judge_model=plan["judge"].get("model", plan["judge"]["executor"]))
                result["judge_identity"] = _identity(plan["judge"], JUDGE_FIELDS)
                _prune(path.parent)
            passed = None
            result.pop("judge_stale", None)
            if result["status"] == "ok" and "check_error" not in checks:
                passed = all(checks.get(n) is True for n in spec.get("required", []))
                if spec.get("judge") and plan.get("judge") and spec.get("judge_required", True):
                    if _judged_by(result, plan["judge"]):
                        v = result["judge"].get("verdict")
                        passed = None if v == "error" else passed and v == "pass"
                    else:  # unjudged, or judged by another judge: invalid until re-judged
                        passed, result["judge_stale"] = None, True
            result.update(checks=checks, passed=passed, rechecked=True, rejudged=bool(rejudge))
            _write_json(path, result)
            return 1

        with cf.ThreadPoolExecutor(jobs) as pool:
            count = sum(pool.map(finish, scored, verdicts))
        if judge is not None:
            plan["resolved"] = _record_resolutions(plan.get("resolved"), [plan["judge"]])
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


def summarize(out: Path, as_json=False, group=False):
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
    if as_json:
        return json.dumps({f"{s}|{a}": v for (s, a), v in table.items()}, indent=1)
    lines = [f"# Trial summary: {out.name}", "",
             "Passed / valid runs (95% Wilson interval). A run is valid when the executor finished "
             "and its checks ran; invalid runs are listed separately (judge-stale: no verdict from the run "
             "directory's judge, which `trial.py recheck --rejudge` gives; judge-error: the judge gave no verdict).", "",
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
    lines += ["", "| Arm | passed | valid | mean output tokens | mean commands | mean seconds |",
              "|---|---|---|---|---|---|"]
    for a in arms:
        rs = [r for r in results if r["arm"] == a]
        ok = [r for r in rs if r["passed"] is not None]
        mean = lambda xs: sum(xs) / len(xs) if xs else 0
        lines.append(f"| {a} | {sum(1 for r in ok if r['passed'])} | {len(ok)} | "
                     f"{mean([r.get('usage', {}).get('output_tokens', 0) for r in ok]):.0f} | "
                     f"{mean([r.get('commands', 0) for r in ok]):.1f} | "
                     f"{mean([r.get('seconds', 0) for r in ok]):.0f} |")
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
    r.add_argument("--dry-run", action="store_true",
                   help="print the models and schedule and exit; asks no endpoint, so a latest: spec the run directory "
                        "has not resolved (and TRIAL_MODELS_FILE cannot answer) shows unresolved")
    d = sub.add_parser("derive", help="write a plan whose arms are artifacts that an earlier run produced")
    d.add_argument("out", type=Path, help="the earlier run directory")
    d.add_argument("--scenario", required=True, help="scenario in the earlier run whose runs produced the artifact")
    d.add_argument("--artifact", required=True, help="path of the artifact inside each run's working directory")
    d.add_argument("--consumer", required=True, type=Path, help="scenario directory the derived arms run")
    d.add_argument("--executor", default="{}", help='base arm as JSON (default: codex with ${TRIAL_CODEX_MODEL:-latest:gpt-*-luna}), e.g. {"executor": "claude", "model": "latest:claude-sonnet-*", "base_url": "..."}')
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
    m = sub.add_parser("models", help="list model IDs an endpoint serves (the Codex model provider by default)")
    m.add_argument("--match", help="glob to filter, e.g. 'claude-sonnet-*'; with --latest each * stands for a version number")
    m.add_argument("--latest", action="store_true", help="print only what latest:MATCH resolves to")
    m.add_argument("--base-url", help="an Anthropic-compatible endpoint to ask instead of the Codex provider (with the "
                                      "Codex provider's key unless --env-file or --api-key-var name another)")
    m.add_argument("--env-file", help="file holding the key (default: codex.env in the Codex home)")
    m.add_argument("--api-key-var", help="variable in the env file holding the key (default: the Codex provider's env_key)")
    s = sub.add_parser("summarize", help="summarize a run directory")
    s.add_argument("out", type=Path)
    s.add_argument("--json", action="store_true")
    s.add_argument("--group", action="store_true", help="pool derived arms by their source arm (the part before '~')")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "summarize":
            print(summarize(a.out, a.json, a.group))
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
                raise TrialError("--executor must be a JSON object, e.g. {\"executor\": \"codex\", \"model\": \"gpt-6-luna\"}")
            n = derive(a.out, a.scenario, a.artifact, a.consumer, base, a.repeats, a.plan)
            print(f"wrote {a.plan} with {n} derived arms")
            return 0
        if a.cmd == "recheck":
            judge = _check_judge(_json_arg(a.judge, "--judge"), "--judge") if a.judge is not None else None
            print(f"rechecked {recheck(a.out, a.rejudge, a.jobs, judge, a.only.split(',') if a.only else None)} runs")
            print(summarize(a.out))
            return 0
        only, arms = (a.only.split(",") if a.only else None), (a.arms.split(",") if a.arms else None)
        out = a.out.resolve() if a.out else None
        # Validate the plan, and resolve its models, before any directory exists; a dry run asks no endpoint.
        plan = load_plan(a.plan.resolve(), a.repeats, only, arms, _stored_plan(out) if out else {}, query=not a.dry_run)
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
        out.mkdir(parents=True, exist_ok=True)
        with _lock(out):
            plan = load_plan(a.plan.resolve(), a.repeats, only, arms, _stored_plan(out))
            _snapshot_instructions(plan, out)
            jobs = schedule(plan)
            _write_json(out / "plan.json", _merge_stored_plan(out, plan))
            print(f"run directory: {out}", flush=True)
            with cf.ThreadPoolExecutor(a.jobs) as pool:
                for res in pool.map(lambda j: run_job(plan, out, j, a.retry_invalid), jobs):
                    print(f"{res['job']}\t{res['status']}\tpassed={res['passed']}", flush=True)
            summary = summarize(out)
            (out / "summary.md").write_text(summary + "\n")
        print(summary)
        return 0
    except TrialError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
