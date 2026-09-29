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

Plan (paths relative to the plan file):

    {"name": "kernel-screen", "repeats": 5, "seed": 1,
     "arms": {"none":   {"executor": "codex", "model": "gpt-6-luna", "effort": "high"},
              "kernel": {"executor": "codex", "model": "gpt-6-luna", "effort": "high",
                         "instructions": "arms/kernel.md"}},
     "scenarios": ["../scenarios/blocked-deploy"],
     "judge": {"executor": "codex", "model": "gpt-6-luna", "effort": "high"}}

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
import datetime as dt
import importlib.util
import json
import math
import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import tomllib
from pathlib import Path

DEFAULT_OUT = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "agent-trials"
CODEX_HOME_SRC = Path(os.environ.get("TRIAL_CODEX_SOURCE_HOME", Path.home() / ".codex"))


class TrialError(Exception):
    pass


# ---------------------------------------------------------------- plan loading

def load_plan(path: Path, repeats: int | None, only: list[str] | None, arms: list[str] | None):
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
        arm = dict(arm)
        if arm.get("instructions"):
            arm["instructions"] = str((base / Path(arm["instructions"]).expanduser()).resolve())
        selected[name] = arm
    if not selected:
        raise TrialError("no arms selected; valid arms: " + ", ".join(plan["arms"]))
    plan["arms"] = selected
    plan["scenarios"] = scenarios
    if plan.get("judge", {}).get("instructions"):
        plan["judge"]["instructions"] = str((base / plan["judge"]["instructions"]).resolve())
    return plan


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


def _env_file_prefix(env_file: Path | None) -> list[str]:
    """Load the provider credential file into the child process only; never read here."""
    if env_file and env_file.exists():
        return ["sh", "-c", 'set -a; . "$0" >/dev/null 2>&1; set +a; exec "$@"', str(env_file)]
    return []


def _run(cmd, *, cwd, env, stdin_text, timeout, stdout_path, stderr_path):
    with open(stdout_path, "ab") as out, open(stderr_path, "ab") as err:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=out,
                                stderr=err, start_new_session=True)
        try:
            proc.communicate(stdin_text.encode() if stdin_text is not None else None, timeout=timeout)
            return proc.returncode, False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            return None, True


def confine_prefix(job_dir: Path, readable: list[Path]) -> list[str]:
    """Wrap a command in bubblewrap: the host is read-only, the user's home is hidden, and only
    the run directory is writable. Network stays available for model APIs."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise TrialError("confined runs need bubblewrap (bwrap); install it or set \"sandbox\" explicitly")
    cmd = [bwrap, "--ro-bind", "/", "/", "--tmpfs", str(Path.home()), "--dev", "/dev", "--proc", "/proc",
           "--tmpfs", "/tmp", "--die-with-parent"]
    for path in readable:
        if path.exists():
            cmd += ["--ro-bind", str(path), str(path)]
    return cmd + ["--bind", str(job_dir), str(job_dir), "--chdir", str(job_dir / "work"), "--"]


def _codex_sandbox(spec):
    """'confined' (default) runs Codex unsandboxed inside bubblewrap so agents can commit;
    any other value is passed to Codex's own sandbox."""
    mode = spec.get("sandbox", "confined")
    return ("danger-full-access", True) if mode == "confined" else (mode, False)


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
    prefix = _env_file_prefix(env_file)
    codex = arm.get("binary") or shutil.which("codex", path=str(Path.home() / ".npm-global/bin")) or "codex"
    sandbox, confined = _codex_sandbox(spec)
    if confined:
        install = Path(codex).resolve().parents[3] if Path(codex).exists() else Path(codex).parent
        prefix = confine_prefix(job_dir, [install, Path(codex).parent, env_file,
                                          *[Path(p).expanduser() for p in arm.get("readable", [])]]) + prefix
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


def _provider_key_var():
    """Name of the environment variable holding the Codex model provider's key (read from config, never its value)."""
    src = CODEX_HOME_SRC / "config.toml"
    if src.exists():
        cfg = tomllib.loads(src.read_text())
        block = cfg.get("model_providers", {}).get(cfg.get("model_provider") or "", {})
        return block.get("env_key")
    return None


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
    return dict(env, ANTHROPIC_BASE_URL=arm["base_url"]), [
        "sh", "-c", 'set -a; . "$0" >/dev/null 2>&1; set +a; eval "export ANTHROPIC_API_KEY=\\$$1"; shift; exec "$@"',
        str(env_file), var]


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
        before = len(_read(job_dir / "events.jsonl").splitlines())
        code, timed_out = _run(c, cwd=job_dir / "work", env=env, stdin_text=prompt, timeout=timeout,
                               stdout_path=job_dir / "events.jsonl", stderr_path=job_dir / "stderr.log")
        for line in _read(job_dir / "events.jsonl").splitlines()[before:]:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "result" and isinstance(event.get("result"), str):
                (job_dir / f"final-{i}.md").write_text(event["result"])
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
        for line in events.read_text().splitlines():
            if '"thread.started"' in line:
                try:
                    return json.loads(line)["thread_id"]
                except (json.JSONDecodeError, KeyError):
                    pass
    return None


# ---------------------------------------------------------------- run record

class Run:
    """What a check sees: the resulting state and the native record of one run."""

    def __init__(self, job_dir: Path, status: str):
        self.dir = job_dir
        self.workdir = job_dir / "work"
        self.harness = job_dir / "harness"
        self.status = status
        self.events = []
        for line in _read(job_dir / "events.jsonl").splitlines():
            try:
                self.events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        self.messages = [t for t in (_message_text(e) for e in self.events) if t]
        finals = sorted(job_dir.glob("final-*.md"))
        self.final_message = _read(finals[-1]) if finals else (self.messages[-1] if self.messages else "")
        self.commands = [c for c in (_command_text(e) for e in self.events) if c]
        self.calls = []
        for line in _read(self.harness / "calls.jsonl").splitlines():
            try:
                self.calls.append(json.loads(line))
            except json.JSONDecodeError:
                self.calls.append({"raw": line})
        self.usage = _usage(self.events)

    def git(self, *args, cwd=None) -> str:
        r = subprocess.run(["git", *args], cwd=cwd or self.workdir, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""

    def file(self, rel: str) -> str:
        return _read(self.workdir / rel)


def _write_json(path: Path, obj):
    """Write atomically, so a reader never sees a partial result."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, path)


def _load_results(out: Path):
    """Finished results; unreadable ones (interrupted writes) are skipped and counted."""
    results, skipped = [], 0
    for p in sorted((out / "runs").glob("*/result.json")):
        try:
            results.append((p, json.loads(p.read_text())))
        except (OSError, json.JSONDecodeError):
            skipped += 1
    return results, skipped


def _read(p: Path) -> str:
    try:
        return p.read_text(errors="replace")
    except OSError:
        return ""


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


def judge_run(plan, spec, run: Run, checks_mod, job_dir: Path, env):
    """Blind verdict on one run: the judge sees the task and evidence, never the arm."""
    j = spec.get("judge")
    if not j or not plan.get("judge"):
        return None
    evidence = checks_mod.judge_context(run) if checks_mod and hasattr(checks_mod, "judge_context") else ""
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
    jd = job_dir / "judge"
    jd.mkdir(exist_ok=True)
    (jd / "work").mkdir(exist_ok=True)
    (jd / "harness").mkdir(exist_ok=True)
    (jd / "prompt.md").write_text(prompt)
    jarm = dict(plan["judge"])
    if jarm["executor"] == "codex":
        schema = jd / "schema.json"
        schema.write_text(json.dumps(JUDGE_SCHEMA))
        home = jd / "home"
        home.mkdir(exist_ok=True)
        (home / "config.toml").write_text(_provider_config(jarm["model"], jarm.get("effort", "high")))
        cache = CODEX_HOME_SRC / "models_cache.json"
        if cache.exists():
            shutil.copy(cache, home / "models_cache.json")
        codex = jarm.get("binary") or shutil.which("codex", path=str(Path.home() / ".npm-global/bin")) or "codex"
        cmd = _env_file_prefix(Path(jarm.get("env_file", CODEX_HOME_SRC / "codex.env"))) + [
            codex, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-m", jarm["model"],
            "-c", f"model_reasoning_effort={jarm.get('effort', 'high')}", "-C", str(jd / "work"),
            "--output-schema", str(schema), "-o", str(jd / "verdict.json"), "-"]
        _run(cmd, cwd=jd / "work", env=dict(env, CODEX_HOME=str(home)), stdin_text=prompt,
             timeout=600, stdout_path=jd / "events.jsonl", stderr_path=jd / "stderr.log")
    elif jarm["executor"] == "claude":
        jenv, prefix = _claude_proxy(jarm, env)
        cmd = prefix + [_claude_binary(jarm), "-p", "--bare", "--model", jarm["model"],
                        "--output-format", "json", "--json-schema", json.dumps(JUDGE_SCHEMA)]
        if jarm.get("effort"):
            cmd += ["--effort", jarm["effort"]]
        _run(cmd, cwd=jd / "work", env=jenv, stdin_text=prompt, timeout=600,
             stdout_path=jd / "verdict.raw.json", stderr_path=jd / "stderr.log")
        raw = _read(jd / "verdict.raw.json")
        try:
            out = json.loads(raw)
            (jd / "verdict.json").write_text(json.dumps(out.get("structured_output") or json.loads(out["result"])))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    try:
        return json.loads(_read(jd / "verdict.json"))
    except json.JSONDecodeError:
        return {"verdict": "error", "reason": "judge produced no verdict"}


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
    """Remove per-run caches that hold no evidence (host plugin catalogs, bundled skill copies)."""
    for rel in PRUNE:
        target = job_dir / rel
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()


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
                      "status": "setup-failed", "passed": None}
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
            passed = passed and (verdict or {}).get("verdict") == "pass"
    result = {"job": job_id, "arm": arm_name, "scenario": spec["name"], "repeat": rep, "status": status,
              "passed": passed, "checks": checks, "judge": verdict, "usage": run.usage,
              "commands": len(run.commands),
              "seconds": round((dt.datetime.now(dt.timezone.utc) - started).total_seconds(), 1)}
    _write_json(result_path, result)
    _prune(job_dir)
    return result


def derive(out: Path, scenario: str, artifact: str, consumer: Path, base: dict, repeats: int, plan_path: Path) -> int:
    """A second-stage plan: each artifact an earlier run produced becomes an arm's instructions.

    Arm names are '<source arm>~r<repeat>', so `summarize --group` pools each source arm's artifacts."""
    arms_dir = plan_path.parent / (plan_path.stem + "-arms")
    arms_dir.mkdir(parents=True, exist_ok=True)
    arms = {}
    for path, result in _load_results(out)[0]:
        if result.get("scenario") != scenario:
            continue
        produced = path.parent / "work" / artifact
        if result.get("status") != "ok" or not produced.is_file():
            continue
        name = f"{result['arm']}~r{result['repeat']}"
        target = arms_dir / f"{name.replace('~', '__')}.md"
        shutil.copy(produced, target)
        arms[name] = dict(base or {"executor": "codex", "model": "gpt-6-luna", "effort": "high"},
                          instructions=str(target.relative_to(plan_path.parent)))
    if not arms:
        raise TrialError(f"no finished '{scenario}' runs with {artifact} under {out / 'runs'}")
    plan = {"name": plan_path.stem, "repeats": repeats, "seed": 1, "arms": arms,
            "scenarios": [os.path.relpath(consumer.resolve(), plan_path.parent.resolve())]}
    plan_path.write_text(json.dumps(plan, indent=1))
    return len(arms)


def recheck(out: Path, rejudge=False, jobs=6, judge=None, only=None) -> int:
    """Re-score finished runs with the scenarios' current checks, and optionally their current judge.

    Without rejudge, stored judge verdicts are kept. With it, the judge runs again on the stored run
    (its final message and resulting state) using the scenario's current question and evidence;
    `judge` replaces the plan's judge for that pass and implies rejudge."""
    plan = json.loads((out / "plan.json").read_text())
    if judge:
        plan, rejudge = dict(plan, judge=judge), True
    specs = {s["name"]: s for s in plan["scenarios"]}
    loaded, _ = _load_results(out)
    if only:
        loaded = [(path, r) for path, r in loaded if r["scenario"] in only]

    def one(item):
        path, result = item
        spec = specs.get(result["scenario"])
        if not spec or result["status"] == "setup-failed":
            return 0
        spec = dict(spec, **json.loads((Path(spec["dir"]) / "scenario.json").read_text()))
        run = Run(path.parent, result["status"])
        mod, checks = _checks_for(spec, run)
        if rejudge and result["status"] == "ok" and spec.get("judge") and plan.get("judge") and "check_error" not in checks:
            shutil.rmtree(path.parent / "judge", ignore_errors=True)
            result["judge"] = judge_run(plan, spec, run, mod, path.parent, isolated_env(path.parent, out, spec))
            result["judge"]["judge_model"] = plan["judge"].get("model", plan["judge"]["executor"])
            _prune(path.parent)
        passed = None
        if result["status"] == "ok" and "check_error" not in checks:
            passed = all(checks.get(n) is True for n in spec.get("required", []))
            if spec.get("judge") and plan.get("judge") and spec.get("judge_required", True):
                passed = passed and (result.get("judge") or {}).get("verdict") == "pass"
        result.update(checks=checks, passed=passed, rechecked=True, rejudged=bool(rejudge))
        _write_json(path, result)
        return 1

    with cf.ThreadPoolExecutor(jobs) as pool:
        return sum(pool.map(one, loaded))


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
                             "invalid": sorted({(r["status"] if r["status"] != "ok" else "check-error")
                                                for r in rs if r["passed"] is None}),
                             "interval": wilson(k, len(ok)),
                             "checks": _check_rates(ok)}
    if as_json:
        return json.dumps({f"{s}|{a}": v for (s, a), v in table.items()}, indent=1)
    lines = [f"# Trial summary: {out.name}", "",
             "Passed / valid runs (95% Wilson interval). A run is valid when the executor finished "
             "and its checks ran; invalid runs are listed separately.", "",
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
    r.add_argument("--dry-run", action="store_true", help="print the schedule and exit")
    d = sub.add_parser("derive", help="write a plan whose arms are artifacts that an earlier run produced")
    d.add_argument("out", type=Path, help="the earlier run directory")
    d.add_argument("--scenario", required=True, help="scenario in the earlier run whose runs produced the artifact")
    d.add_argument("--artifact", required=True, help="path of the artifact inside each run's working directory")
    d.add_argument("--consumer", required=True, type=Path, help="scenario directory the derived arms run")
    d.add_argument("--executor", default="{}", help='base arm as JSON, e.g. {"executor": "codex", "model": "gpt-6-luna"}')
    d.add_argument("--repeats", type=int, default=2)
    d.add_argument("--plan", required=True, type=Path, help="where to write the derived plan (its arms directory sits beside it)")
    c = sub.add_parser("recheck", help="recompute checks for finished runs after a check changes (no new agent runs)")
    c.add_argument("out", type=Path)
    c.add_argument("--rejudge", action="store_true",
                   help="also rerun the judge with each scenario's current question and evidence")
    c.add_argument("--judge", help='judge as JSON for this pass, replacing the plan\'s, e.g. {"executor": "claude", "model": "claude-sonnet-5"}')
    c.add_argument("--only", help="comma-separated scenario names to re-score")
    c.add_argument("--jobs", type=int, default=6)
    s = sub.add_parser("summarize", help="summarize a run directory")
    s.add_argument("out", type=Path)
    s.add_argument("--json", action="store_true")
    s.add_argument("--group", action="store_true", help="pool derived arms by their source arm (the part before '~')")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "summarize":
            print(summarize(a.out, a.json, a.group))
            return 0
        if a.cmd == "derive":
            n = derive(a.out, a.scenario, a.artifact, a.consumer, json.loads(a.executor), a.repeats, a.plan)
            print(f"wrote {a.plan} with {n} derived arms")
            return 0
        if a.cmd == "recheck":
            print(f"rechecked {recheck(a.out, a.rejudge, a.jobs, json.loads(a.judge) if a.judge else None, a.only.split(',') if a.only else None)} runs")
            print(summarize(a.out))
            return 0
        plan = load_plan(a.plan.resolve(), a.repeats, a.only.split(",") if a.only else None,
                         a.arms.split(",") if a.arms else None)
        jobs = schedule(plan)
        if a.dry_run:
            for arm, spec, rep in jobs:
                print(f"{spec['name']}\t{arm}\tr{rep}")
            return 0
        out = (a.out or DEFAULT_OUT / f"{plan['name']}-{dt.datetime.now():%Y%m%d-%H%M%S}").resolve()
        if any((p / ".git").exists() for p in [out, *out.parents]):
            raise TrialError(f"{out} is inside a git repository; choose --out outside any repository")
        out.mkdir(parents=True, exist_ok=True)
        (out / "plan.json").write_text(json.dumps(plan, indent=1))
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
