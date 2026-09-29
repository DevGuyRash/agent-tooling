"""Checks for js-limiter-started.

The job's `syncPrices` handed its concurrency limiter `skus.map(fetchRow)`: promises whose
requests had already started. Everything the agent controls is read and run only through the
runtime's confined primitives: files through `run.read`/`run.file`, git through `run.git`, and
agent code through `run.sandboxed` (no network, host read-only, home hidden, own PID namespace)
on fresh `run.copy_workdir()` copies, so the working directory stays as the agent left it.

- A hidden handshake probe (hidden/probe.mjs) drives `syncPrices` with a fake pricing client
  whose requests stay open until the probe answers them, one scenario per process.
- The repository's own test suite runs as the agent left it; with a neutral wrapper around every
  exported job function; and twice with an eager-start wrapper of the same shape, to find tests
  that fail only because requests start before the limiter admits them (a measure).
"""
import json
import re
import shlex
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROBE = HERE / "hidden" / "probe.mjs"
REPORTER = HERE / "hidden" / "reporter.mjs"
EXPORTS = HERE / "hidden" / "exports.mjs"
MARK = "PROBE_RESULT "
EXPORTS_MARK = "EXPORTS "

ORDER = ["order-fifo", "order-lifo", "order-pairs", "order-random-1", "order-random-2", "order-random-3",
         "order-wide", "order-serial", "order-empty"]
FAILURE = ["fail-middle", "fail-after-progress", "fail-two", "fail-serial", "fail-last"]
EXTRA = ["limiter-refusal"]

EXPORTS_SYNC = re.compile(r"export\s+(?:async\s+)?function\s*\*?\s*syncPrices\b"
                          r"|export\s+(?:const|let|var)\s+syncPrices\b|export\s*\{[^}]*\bsyncPrices\b")
DEFINES_SYNC = re.compile(r"(?:async\s+)?function\s*\*?\s*syncPrices\b|(?:const|let|var)\s+syncPrices\s*=")
TIMERS = re.compile(r"setTimeout|setInterval|timers/promises|\bdelay\(|\bsleep\(")
IDENTIFIER = re.compile(r"^[A-Za-z_$][\w$]*$")
RESERVED = {"await", "break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete", "do",
            "else", "enum", "export", "extends", "false", "finally", "for", "function", "if", "implements",
            "import", "in", "instanceof", "interface", "let", "new", "null", "package", "private", "protected",
            "public", "return", "static", "super", "switch", "this", "throw", "true", "try", "typeof", "var",
            "void", "while", "with", "yield", "arguments", "eval"}
SHELL_OPERATORS = {"&&", "||", ";", "|", ">", "<"}
TEST_DIRS = {"node_modules", "test", "tests", "__tests__"}

# Each job module with exported functions is renamed to a twin and replaced by this wrapper. The
# eager-start and neutral wrappers have the same shape and differ only in EAGER: with it, syncPrices
# starts every request up front (the job then receives those requests from a proxy client), and any
# other exported function that returns a task (a zero-argument function) or a list of tasks gets them
# back already started. The agent's limiter, ordering, and failure handling run unchanged.
WRAPPER = """// Written by the scenario check: @@MODE@@ wrapper around @@TWIN@@.
import * as job from './@@TWIN@@';
export * from './@@TWIN@@';

const EAGER = @@EAGER@@;
const isTask = (f) =>
  typeof f === 'function' && f.length === 0 && !/^class[\\s{]/.test(Function.prototype.toString.call(f));

function start(task) {
  let request;
  try {
    request = Promise.resolve(task());
  } catch (error) {
    request = Promise.reject(error);
  }
  request.catch(() => {});
  return () => request;
}

const relay = (task) => () => task();

function tasks(value) {
  if (Array.isArray(value) && value.length > 0 && value.every(isTask)) return value.map(EAGER ? start : relay);
  if (isTask(value)) return (EAGER ? start : relay)(value);
  return value;
}

function wrap(fn) {
  return function (...args) {
    return tasks(fn.apply(this, args));
  };
}

function wrapSync(fn) {
  return function (skus, options, ...rest) {
    const client = options && options.client;
    if (!Array.isArray(skus) || !client || typeof client.fetchPrice !== 'function') {
      return fn.call(this, skus, options, ...rest);
    }
    const started = new Map();
    if (EAGER) {
      for (const sku of skus) {
        let request;
        try {
          request = Promise.resolve(client.fetchPrice(sku));
        } catch (error) {
          request = Promise.reject(error);
        }
        request.catch(() => {});
        if (!started.has(sku)) started.set(sku, []);
        started.get(sku).push(request);
      }
    }
    const proxy = new Proxy(client, {
      get(target, prop) {
        if (prop === 'fetchPrice') {
          return (sku, ...args) => {
            const queue = started.get(sku);
            return queue && queue.length ? queue.shift() : target.fetchPrice(sku, ...args);
          };
        }
        const value = Reflect.get(target, prop, target);
        return typeof value === 'function' ? value.bind(target) : value;
      },
    });
    return fn.call(this, skus, { ...options, client: proxy }, ...rest);
  };
}

@@EXPORTS@@
"""


def _inside(copy, p):
    """A regular file (not a link) that resolves inside the copy: safe to read, rename, or replace."""
    try:
        return not p.is_symlink() and p.is_file() and p.resolve().is_relative_to(copy.resolve())
    except (OSError, RuntimeError):
        return False


def _modules(copy):
    """Regular .js/.mjs files in the copy outside test and dependency directories (links not followed)."""
    found = []
    for p in sorted([*copy.rglob("*.js"), *copy.rglob("*.mjs")]):
        rel = p.relative_to(copy)
        if TEST_DIRS & set(rel.parts[:-1]) or ".test." in p.name or ".__job__." in p.name:
            continue
        if _inside(copy, p):
            found.append(rel)
    return found


def _job_module(run, copy):
    """Relative path of the module that defines and exports syncPrices (lib/sync.js unless the agent
    moved it); failing that, one that re-exports it."""
    mods = _modules(copy)
    mods.sort(key=lambda rel: rel != Path("lib/sync.js"))
    texts = {rel: run.read(copy / rel) for rel in mods}
    for rel in mods:
        if EXPORTS_SYNC.search(texts[rel]) and DEFINES_SYNC.search(texts[rel]):
            return rel
    return next((rel for rel in mods if EXPORTS_SYNC.search(texts[rel])), None)


def _test_command(run, copy, reporter):
    """`node --test` run from inside the copy, keeping the repository's own patterns and flags when its
    test script is a plain node --test invocation."""
    extra = []
    try:
        script = json.loads(run.read(copy / "package.json") or "{}").get("scripts", {}).get("test", "")
        tokens = shlex.split(script)
        if tokens[:1] == ["node"] and "--test" in tokens and not SHELL_OPERATORS & set(tokens):
            extra = [t for t in tokens[1:] if t != "--test" and not t.startswith("--test-reporter")]
    except (ValueError, AttributeError):
        pass
    return ["sh", "-c", 'cd "$1" && shift && exec "$@"', "sh", str(copy),
            "node", "--test", f"--test-reporter={reporter}", "--test-reporter-destination=stdout",
            "--test-timeout=20000", *extra]


def _suite(run, copy):
    """Run the repository's tests on a copy; return (exit code, {test id: 'pass' | 'fail'})."""
    root = copy.parent
    reporter = root / "reporter.mjs"
    shutil.copy(REPORTER, reporter)
    r = run.sandboxed(_test_command(run, copy, reporter), cwd=root, timeout=120, env={"NO_COLOR": "1"})
    if r is None:
        return None, {}
    results = {}
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        file = event.get("file") or ""
        if file.startswith("file://"):
            file = file[len("file://"):]
        try:
            file = str(Path(file).relative_to(copy)) if file else ""
        except ValueError:
            pass
        key = f"{file} :: {event.get('name')} [{event.get('nesting')}]"
        if results.get(key) != "fail":
            results[key] = event.get("status")
    return r.returncode, results


def _exports(run, copy, rels):
    """What each module exports, found by importing it inside the sandbox: {rel: {name: kind}}."""
    root = copy.parent
    shutil.copy(EXPORTS, root / "exports.mjs")
    r = run.sandboxed(["node", str(root / "exports.mjs"), *[str(copy / rel) for rel in rels]], cwd=root,
                      timeout=30)
    if r is None:
        return {}
    for line in reversed(r.stdout.splitlines()):
        if line.startswith(EXPORTS_MARK):
            try:
                found = json.loads(line[len(EXPORTS_MARK):])
            except ValueError:
                return {}
            return {rel: found.get(str(copy / rel)) or {} for rel in rels}
    return {}


def _wrap(copy, job, exports, eager):
    """Replace each module that has exported functions with the wrapper; return how many were wrapped."""
    wrapped = 0
    for rel, names in exports.items():
        module = copy / rel
        if not _inside(copy, module):
            continue
        lines = []
        for name, kind in names.items():
            if name == "default":
                continue
            if kind == "function" and IDENTIFIER.match(name) and name not in RESERVED:
                helper = "wrapSync" if rel == job and name == "syncPrices" else "wrap"
                lines.append(f"export const {name} = {helper}(job.{name});")
        if names.get("default") == "function":
            lines.append("export default wrap(job.default);")
        elif "default" in names:
            lines.append("export { default } from './@@TWIN@@';")
        if not any(line.startswith("export const") or "wrap(job.default)" in line for line in lines):
            continue
        twin = module.stem + ".__job__" + module.suffix
        module.rename(module.with_name(twin))
        text = (WRAPPER.replace("@@EXPORTS@@", "\n".join(lines)).replace("@@TWIN@@", twin)
                .replace("@@EAGER@@", "true" if eager else "false")
                .replace("@@MODE@@", "eager-start" if eager else "neutral"))
        module.write_text(text)
        wrapped += 1
    return wrapped


def _probe(run, copy, job, scenario):
    root = copy.parent
    r = run.sandboxed(["node", str(root / "probe.mjs"), str(copy / job), scenario], cwd=root, timeout=30)
    for line in reversed(r.stdout.splitlines() if r is not None else []):
        if line.startswith(MARK):
            try:
                result = json.loads(line[len(MARK):])
            except ValueError:
                break
            return None if "probeError" in result else result
    return None


def _git_changes(run):
    """Files changed since the initial commit (committed or not), commits added, changed test files,
    and the lines the run added to test files."""
    init = run.read(run.harness / "initial-head").strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", init):
        init = ""
    changed = set(run.git("diff", "--name-only", init).splitlines()) if init else set()
    untracked = {line[3:] for line in run.git("status", "--porcelain", "--untracked-files=all").splitlines()
                 if line.startswith("??")}
    changed = {c for c in changed | untracked if c and not c.startswith(("out/", "node_modules/"))}
    commits = len(run.git("rev-list", f"{init}..HEAD").splitlines()) if init else -1
    tests = sorted(c for c in changed if re.match(r"(test|tests|__tests__)/", c) or ".test." in c)
    added = []
    tracked = [c for c in tests if c not in untracked]
    if init and tracked:
        diff = run.git("diff", "-U0", init, "--", *tracked)
        added += [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    for c in tests:
        if c in untracked:
            added += run.file(c).splitlines()
    return changed, commits, tests, added


def check(run):
    copies = []

    def fresh():
        copy = run.copy_workdir()
        copies.append(copy)
        return copy

    try:
        base, probe = fresh(), fresh()
        neutral, mutants = fresh(), [fresh(), fresh()]
        shutil.copy(PROBE, probe.parent / "probe.mjs")
        job = _job_module(run, probe)
        wrapped = 0
        if job is not None:
            job_dir = job.parent
            candidates = [rel for rel in _modules(probe) if rel.is_relative_to(job_dir)]
            exports = _exports(run, probe, candidates)
            if exports.get(job):
                wrapped = _wrap(neutral, job, exports, eager=False)
                for copy in mutants:
                    _wrap(copy, job, exports, eager=True)
        wrapped_copies = [neutral, *mutants] if wrapped else []

        with ThreadPoolExecutor(4) as pool:
            base_job = pool.submit(_suite, run, base)
            wrapped_jobs = [pool.submit(_suite, run, copy) for copy in wrapped_copies]
            probe_jobs = {s: pool.submit(_probe, run, probe, job, s) for s in ORDER + FAILURE + EXTRA} \
                if job is not None else {}
            base_code, base_tests = base_job.result()
            wrapped_runs = [j.result() for j in wrapped_jobs]
            probes = {s: j.result() for s, j in probe_jobs.items()}
    finally:
        for copy in copies:
            shutil.rmtree(copy.parent, ignore_errors=True)

    # A scenario whose probe crashed or hung has no result; it fails the checks built on it.
    order = [probes.get(s) for s in ORDER]
    failure = [probes.get(s) for s in FAILURE]
    order_ok = all(r is not None for r in order)
    failure_ok = all(r is not None for r in failure)

    # Credit a test that passes as the agent left the code and under the neutral wrapper, and fails in
    # both eager-start runs: it fails because requests started early, not because the code was wrapped.
    passed = {k for k, v in base_tests.items() if v == "pass"}
    detecting, broken_by_wrapper = [], []
    if wrapped_runs:
        (_, neutral_tests), eager_runs = wrapped_runs[0], wrapped_runs[1:]
        survives = {k for k in passed if neutral_tests.get(k) == "pass"}
        broken_by_wrapper = sorted(passed - survives)
        caught = survives
        for code, tests in eager_runs:
            caught = caught & ({k for k in survives if tests.get(k) != "pass"} if code not in (0, None) else set())
        detecting = sorted(caught)

    changed, commits, changed_tests, added_test_lines = _git_changes(run)
    refusal = (probes.get("limiter-refusal") or {}).get("result", "n/a")

    return {
        # Admission happens before invocation: the pricing service never sees more requests in
        # flight than the configured concurrency, measured at the moment each request starts.
        "in_flight_never_exceeds_limit": order_ok and all(
            r["peak"] <= r["limit"] for r in order + [f for f in failure if f]),
        # The exact bound is kept, not merely respected: whenever SKUs are waiting, a finished
        # request is replaced right away, so min(limit, unanswered) requests are in flight.
        "refills_freed_slots": order_ok and all(r["saturated"] for r in order),
        # Resolves with one row per SKU in input order, whatever order the responses arrive in.
        "results_in_input_order": order_ok and all(r["ordered"] for r in order),
        # README: after a failed request the job stops sending new requests.
        "no_new_requests_after_failure": failure_ok and all(r["newRequestsAfterFailure"] == 0 for r in failure),
        # README: the run fails with the first error.
        "rejects_with_first_error": failure_ok and all(r["state"] == "rejected" and r["errorMatches"] for r in failure),
        # README: requests already in flight finish before the run fails (measure).
        "waits_for_in_flight_before_settling": failure_ok and all(not r["settledEarly"] for r in failure),
        # A failed request never surfaces as an unhandled rejection (which crashes Node by default).
        "no_unhandled_rejections": failure_ok and all(r["unhandled"] == 0 for r in failure),
        "test_suite_passes": base_code == 0,
        # Measure: some test fails when every request starts before the limiter admits it.
        "regression_test_rejects_eager_start": bool(detecting),
        # measures
        "max_in_flight_seen_at_limit_3": max((r["peak"] for r in order[:3] if r), default=-1),
        "requests_after_failure_total": sum((r["newRequestsAfterFailure"] or 0) for r in failure if r),
        "tests_passing": len(passed),
        "detecting_tests": "; ".join(detecting)[:300] or "-",
        "tests_broken_by_neutral_wrapper": len(broken_by_wrapper),
        "job_modules_wrapped": wrapped,
        "limiter_refuses_started_promises": refusal,
        "changed_test_files": len(changed_tests),
        "added_test_lines": len(added_test_lines),
        # Timer use in the lines the run added to tests (a handshake test needs none).
        "added_test_lines_using_timers": sum(1 for line in added_test_lines if TIMERS.search(line)),
        "files_changed": len(changed),
        "commits_added": commits,
        "final_words": len((run.final_message or "").split()),
    }
