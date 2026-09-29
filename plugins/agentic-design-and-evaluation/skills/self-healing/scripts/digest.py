#!/usr/bin/env python3
"""Evidence digest of agent sessions across hosts, for a heal review.

Reads native session logs (Codex rollouts, Claude Code transcripts, Gemini CLI chats), the
git state of repositories, and any Friction Diagnostics stores. It prints what can be counted
or quoted without interpretation: per-thread facts, the user's corrections and "continue"
nudges paired with the agent message that preceded them, repeated failing command shapes,
instruction files the agents read, and leftover worktrees and merged branches. It never prints
command output or file contents, and it masks token-like strings in quoted messages.

    digest.py [--since 7d|YYYY-MM-DD] [--until YYYY-MM-DD] [--codex DIR] [--claude DIR]
              [--gemini DIR] [--repos DIR ...] [--friction DIR ...] [--max-items N] [--json]
    digest.py show SESSION_ID [--at TIMESTAMP] [--context N] [log-dir options]

`show` prints the visible user and agent messages of one session (optionally around a
timestamp) so an incident can be read without loading the whole log.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
UTC = dt.timezone.utc

INJECTED = re.compile(r"^\s*(<[a-z_-]+[\s>/]|# AGENTS\.md|# CLAUDE\.md|Caveat: The messages below)", re.I)
HEARTBEAT = re.compile(r"(?i)^\s*<heartbeat|\[automation\]")
NUDGE = re.compile(r"(?i)^\s*(ok(ay)?[,. ]+)?(please\s+)?(continue|keep going|go on|proceed|carry on|resume|next|go ahead|do it|finish( it)?|don'?t stop\b.*)[\s.!]*$")
CORRECTION = re.compile(
    r"(?i)(^\s*(no\b|nope\b|stop\b|wait\b|don'?t\b|do not\b|why\b|i said|i told you|that'?s not|not what i|wrong\b)"
    r"|why did you|why are you|why is it|you should have|you were supposed|i (already )?(said|asked|told)"
    r"|stop being|instead of|again\?|still (not|isn'?t|doesn'?t)|not (done|finished|complete)"
    r"|remember,? )")
TOKENISH = re.compile(r"(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}"
                      r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
                      r"|(?=[A-Za-z0-9+_=-]*\d)(?=[A-Za-z0-9+_=-]*[A-Za-z])[A-Za-z0-9+_=-]{40,})")
NO_MATCH_OK = {"rg", "grep", "diff", "test", "[", "cmp"}
SKILL_READ = re.compile(r"([\w.@-]+)/SKILL\.md")
INTERPRETERS = {"python", "python3", "node", "bash", "sh", "zsh", "uv", "uvx", "npx", "bunx", "pnpm", "npm", "just",
                "make", "cargo", "go", "deno", "bun", "ruby", "perl", "pwsh"}
ENV_ASSIGN = re.compile(r"^(?:[A-Z_][A-Z0-9_]*=\S*\s+)+")


def mask(text: str, limit: int) -> str:
    text = TOKENISH.sub("[masked]", " ".join((text or "").split()))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def tail(text: str, limit: int) -> str:
    text = TOKENISH.sub("[masked]", " ".join((text or "").split()))
    return text if len(text) <= limit else "…" + text[-(limit - 1):]


def parse_when(value: str | None, default=None):
    if not value:
        return default
    m = re.fullmatch(r"(\d+)d", value)
    if m:
        return dt.datetime.now(UTC) - dt.timedelta(days=int(m.group(1)))
    return dt.datetime.fromisoformat(value).replace(tzinfo=UTC)


def stamp(ts):
    if isinstance(ts, (int, float)):
        return dt.datetime.fromtimestamp(ts, UTC)
    try:
        t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def shape(cmd: str) -> str:
    """A command's shape: the program it runs, without paths, values, or env."""
    cmd = (cmd or "").strip()
    m = re.match(r"^(?:/usr/bin/)?(?:ba|z)?sh\s+-l?c\s+(['\"])(.*)\1\s*$", cmd, re.S)
    if m:
        cmd = m.group(2)
    parts = [p for p in re.split(r"\s*(?:&&|\|\||;|\|)\s*", cmd) if p and not re.match(r"^cd\s", p)]
    first = ENV_ASSIGN.sub("", parts[0] if parts else "").split()
    if not first:
        return "(other)"
    head = first[0].strip("'\"").rsplit("/", 1)[-1]
    words = [head]
    if head in INTERPRETERS:
        # the program an interpreter runs is the meaningful part: `python3 -m pytest`, `node build.mjs`
        for w in first[1:]:
            if w in ("-m", "-c", "run", "exec", "x"):
                words.append(w)
                continue
            if not w.startswith("-"):
                words.append(w.strip("'\"").rsplit("/", 1)[-1][:60])
            break
        return " ".join(words)
    for w in first[1:]:
        if w.startswith("-") or "/" in w or "=" in w or re.search(r"\d{3,}", w) or len(words) >= 3:
            break
        words.append(w.strip("'\""))
    return " ".join(words)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return ""


class Session:
    def __init__(self, host: str, path: Path):
        self.host, self.path, self.id, self.cwd = host, str(path), path.stem, ""
        self.start = self.end = None
        self.timeline: list[tuple[str, str, str]] = []  # (timestamp, role, text)
        self.commands: list[str] = []
        self.failed: list[str] = []
        self.compactions = 0
        self.heartbeats = 0
        self.asks = 0

    def at(self, ts):
        t = stamp(ts)
        if t:
            self.start = t if not self.start or t < self.start else self.start
            self.end = t if not self.end or t > self.end else self.end
        return t.isoformat(timespec="seconds") if t else ""

    def user(self, ts, text):
        if not text or not text.strip():
            return
        if HEARTBEAT.search(text[:200]):
            self.heartbeats += 1
            return
        if INJECTED.match(text):
            return
        self.timeline.append((self.at(ts), "user", text.strip()))

    def agent(self, ts, text):
        if text and text.strip():
            self.timeline.append((self.at(ts), "agent", text.strip()))

    def command(self, cmd, failed):
        self.commands.append(cmd)
        if failed:
            self.failed.append(cmd)

    def signals(self):
        """User messages that correct or re-prompt the agent, each with the agent message before it."""
        out, last_agent = [], ""
        typed = [i for i, (_, role, _) in enumerate(self.timeline) if role == "user"]
        first_user = typed[0] if typed else -1
        for i, (ts, role, text) in enumerate(self.timeline):
            if role == "agent":
                last_agent = text
                continue
            if i == first_user:
                continue
            kind = "nudge" if len(text) <= 200 and NUDGE.match(text) else "correction" if CORRECTION.search(text[:400]) else None
            if kind:
                out.append({"ts": ts, "kind": kind, "user": text, "before": last_agent})
        return out

    def facts(self):
        sig = self.signals()
        creates = lambda rx: sum(1 for c in self.commands if re.search(rx, c))
        return {
            "host": self.host, "session": self.id, "cwd": self.cwd,
            "start": self.start.isoformat(timespec="minutes") if self.start else None,
            "hours": round((self.end - self.start).total_seconds() / 3600, 1) if self.start and self.end else None,
            "user_messages": sum(1 for _, r, _ in self.timeline if r == "user"),
            "nudges": sum(1 for s in sig if s["kind"] == "nudge"),
            "corrections": sum(1 for s in sig if s["kind"] == "correction"),
            "heartbeats": self.heartbeats, "asks_user": self.asks, "compactions": self.compactions,
            "commands": len(self.commands), "failed_commands": len(self.failed),
            "worktrees_added": creates(r"git\s+(-C\s+\S+\s+)?worktree\s+add"),
            "prs_created": creates(r"gh\s+pr\s+create"),
            "automations_created": creates(r"(?i)(automation|heartbeat)[\w-]*\s+(create|add)|crontab\s+-|systemctl\s+--user\s+enable"),
        }


# ---------------------------------------------------------------- readers

CODEX_KEEP = ('"session_meta"', '"item_completed"', '"compacted"', "request_user_input")


def read_codex(path: Path) -> Session:
    s = Session("codex", path)
    with path.open(errors="replace") as fh:
        for line in fh:
            head = line[:300]
            if not any(k in head for k in CODEX_KEEP) or '"Reasoning"' in head[:300]:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            p, t, ts = o.get("payload") or {}, o.get("type"), o.get("timestamp")
            if t == "session_meta":
                s.cwd, s.id = p.get("cwd", s.cwd), p.get("id", s.id)
                s.at(ts)
            elif t == "compacted":
                s.compactions += 1
            elif t == "response_item" and str(p.get("name", "")).startswith("request_user_input"):
                s.asks += 1
            elif t == "event_msg" and p.get("type") == "item_completed":
                it = p.get("item") or {}
                kind = it.get("type")
                if kind == "UserMessage":
                    s.user(ts, _text(it.get("content")))
                elif kind == "AgentMessage":
                    s.agent(ts, _text(it.get("content")))
                elif kind == "CommandExecution":
                    cmd = it.get("command")
                    cmd = cmd[-1] if isinstance(cmd, list) and cmd else str(cmd or "")
                    code = str(it.get("exit_code", "0"))
                    benign = code == "1" and shape(cmd).split(" ")[0] in NO_MATCH_OK
                    s.command(cmd, code not in ("0", "None", "") and not benign)
                    s.at(ts)
    return s


def read_claude(path: Path) -> Session:
    s = Session("claude", path)
    errors = set()
    pending = {}
    with path.open(errors="replace") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("isSidechain"):
                continue
            ts = o.get("timestamp")
            s.cwd = o.get("cwd") or s.cwd
            s.id = o.get("sessionId") or s.id
            if o.get("type") == "system" and "compact" in str(o.get("subtype", "")):
                s.compactions += 1
                continue
            m = o.get("message") or {}
            content = m.get("content")
            if o.get("type") == "user" and not o.get("isMeta") and not o.get("isCompactSummary"):
                if isinstance(content, str):
                    s.user(ts, content)
                elif isinstance(content, list):
                    for b in content:
                        if b.get("type") == "tool_result" and b.get("is_error"):
                            errors.add(b.get("tool_use_id"))
                    text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
                    if text:
                        s.user(ts, text)
            elif o.get("type") == "assistant" and isinstance(content, list):
                text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
                s.agent(ts, text)
                for b in content:
                    if b.get("type") == "tool_use":
                        name, inp = b.get("name"), b.get("input") or {}
                        if name == "Bash":
                            pending[b.get("id")] = str(inp.get("command", ""))
                        elif name == "AskUserQuestion":
                            s.asks += 1
    for tid, cmd in pending.items():
        s.command(cmd, tid in errors)
    return s


def read_gemini(path: Path) -> Session:
    s = Session("gemini", path)
    try:
        d = json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return s
    s.id = d.get("sessionId", s.id)
    for msg in d.get("messages", []):
        ts, kind = msg.get("timestamp"), msg.get("type")
        text = _text(msg.get("content"))
        if kind == "user":
            s.user(ts, text)
        elif kind in ("gemini", "model", "assistant"):
            s.agent(ts, text)
            for call in msg.get("toolCalls") or []:
                args = call.get("args") or {}
                if "command" in args:
                    s.command(str(args["command"]), str(call.get("status", "")).lower() in ("error", "failed"))
    return s


def in_window(path: Path, since, until) -> bool:
    try:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return False
    if since and mtime < since:
        return False
    m = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    if until and m and dt.datetime.fromisoformat(m.group(1)).replace(tzinfo=UTC) > until:
        return False
    return True


def load_sessions(args, since, until):
    sources = []
    if args.codex and Path(args.codex).is_dir():
        sources += [(read_codex, p) for p in Path(args.codex).rglob("*.jsonl")]
    if args.claude and Path(args.claude).is_dir():
        sources += [(read_claude, p) for p in Path(args.claude).rglob("*.jsonl") if "subagents" not in p.parts]
    if args.gemini and Path(args.gemini).is_dir():
        sources += [(read_gemini, p) for p in Path(args.gemini).rglob("chats/*.json")]
    sessions = []
    for reader, path in sources:
        if not in_window(path, since, until):
            continue
        s = reader(path)
        if s.timeline or s.commands:
            sessions.append(s)
    return sessions


def coverage(args, since):
    """Oldest log per host, so a window reaching past a host's retention is visible."""
    out = {}
    for host, root, pattern in (("codex", args.codex, "*.jsonl"), ("claude", args.claude, "*.jsonl"),
                                ("gemini", args.gemini, "chats/*.json")):
        if not root or not Path(root).is_dir():
            out[host] = "absent"
            continue
        times = [p.stat().st_mtime for p in Path(root).rglob(pattern)]
        if not times:
            out[host] = "no logs"
            continue
        oldest = dt.datetime.fromtimestamp(min(times), UTC)
        note = " (window starts before the oldest retained log)" if since and oldest > since else ""
        out[host] = f"{len(times)} logs, oldest {oldest.date()}{note}"
    return out


# ---------------------------------------------------------------- repositories and stores

def git(repo: Path, *args) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def residue(roots, max_items):
    rows = []
    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            continue
        candidates = [root] if (root / ".git").exists() else [p for p in sorted(root.iterdir()) if (p / ".git").is_dir()]
        for repo in candidates:
            default = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").removeprefix("origin/")
            if not default:
                default = next((b for b in ("main", "master") if git(repo, "rev-parse", "--verify", "-q", b)), "")
            if not default:
                continue
            trees = [l[9:] for l in git(repo, "worktree", "list", "--porcelain").splitlines() if l.startswith("worktree ")]
            merged = [b.strip("*+ ").strip() for b in git(repo, "branch", "--merged", default).splitlines()]
            merged = [b for b in merged if b and b != default]
            branches = [b for b in git(repo, "branch", "--format=%(refname:short)").splitlines() if b and b != default]
            if len(trees) > 1 or merged or len(branches) > 3:
                rows.append({"repo": str(repo), "default": default, "extra_worktrees": len(trees) - 1,
                             "local_branches": len(branches), "merged_but_present": len(merged),
                             "examples": merged[:3]})
    rows.sort(key=lambda r: -(r["extra_worktrees"] + r["merged_but_present"]))
    return rows[:max_items]


STOP_CLAUSE = re.compile(r"(?i)[^.]*\b(until|stop|pause|when .{0,40}(complete|done|finished)|once)\b[^.]*\.")


def automations(root: Path, max_items):
    """Agent-created recurring automations with their age and the clause meant to end them."""
    import tomllib
    rows = []
    if not root.is_dir():
        return rows
    now = dt.datetime.now(UTC)
    for f in sorted(root.glob("*/automation.toml")):
        try:
            d = tomllib.loads(f.read_text())
        except (OSError, ValueError):
            continue
        created = d.get("created_at")
        age = round((now - dt.datetime.fromtimestamp(created / 1000, UTC)).total_seconds() / 86400, 1) if created else None
        stop = STOP_CLAUSE.search(d.get("prompt", ""))
        rows.append({"id": d.get("id", f.parent.name), "kind": d.get("kind"), "status": d.get("status"),
                     "schedule": d.get("rrule"), "age_days": age, "thread": d.get("target_thread_id"),
                     "stop_clause": mask(stop.group(0).strip(), 200) if stop else None})
    rows.sort(key=lambda r: (r["status"] != "ACTIVE", -(r["age_days"] or 0)))
    return rows[:max_items]


def friction(roots, max_items):
    files = []
    for root in roots:
        root = Path(root).expanduser()
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files += list(root.glob("*/.local*/reports/friction/events.jsonl")) + list(root.glob(".local*/reports/friction/events.jsonl"))
    records, clusters = 0, collections.defaultdict(lambda: {"n": 0, "repos": set(), "title": ""})
    for f in files:
        repo = f.parents[3].name
        byid = {}
        for line in f.open(errors="replace"):
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            records += 1
            byid[o.get("event_id")] = o
        for o in byid.values():
            anchor = byid.get(o.get("recurs")) if o.get("kind") == "recurrence" else o
            key = (anchor or o).get("recurrence_key") or f"{repo}:{o.get('event_id')}"
            c = clusters[key]
            c["n"] += 1
            c["repos"].add(repo)
            c["title"] = c["title"] or mask((anchor or o).get("title") or (anchor or o).get("actual_outcome", ""), 110)
    recurring = sorted(((k, v) for k, v in clusters.items() if v["n"] > 1), key=lambda kv: -kv[1]["n"])
    return {"stores": len(files), "records": records, "clusters": len(clusters),
            "single_sightings": sum(1 for v in clusters.values() if v["n"] == 1),
            "recurring": [{"key": k, "sightings": v["n"], "repos": sorted(v["repos"]), "title": v["title"]}
                          for k, v in recurring[:max_items]]}


# ---------------------------------------------------------------- report

def build(args):
    since = parse_when(args.since)
    until = parse_when(args.until)
    sessions = load_sessions(args, since, until)
    facts = [s.facts() for s in sessions]
    signals = []
    for s in sessions:
        for sig in s.signals():
            signals.append({"session": s.id, "host": s.host, "cwd": s.cwd, **sig})
    fail_shapes, skill_reads = collections.defaultdict(set), collections.defaultdict(set)
    fail_counts, read_counts = collections.Counter(), collections.Counter()
    for s in sessions:
        for c in s.failed:
            fail_shapes[shape(c)].add(s.id)
            fail_counts[shape(c)] += 1
        for c in s.commands:
            for name in SKILL_READ.findall(c):
                skill_reads[name].add(s.id)
                read_counts[name] += 1
    n = args.max_items
    ranked = sorted(facts, key=lambda f: -(3 * f["corrections"] + 2 * f["nudges"] + f["heartbeats"] + f["worktrees_added"]))
    return {
        "window": {"since": since.date().isoformat() if since else None, "until": until.date().isoformat() if until else None},
        "coverage": coverage(args, since),
        "totals": {"sessions": len(facts),
                   **{k: sum(f[k] or 0 for f in facts) for k in ("user_messages", "nudges", "corrections", "heartbeats",
                                                                 "worktrees_added", "prs_created", "failed_commands")}},
        "threads": ranked[:n],
        "signals": sorted(signals, key=lambda x: x["ts"])[-(n * 3):],
        "failing_shapes": [{"shape": k, "sessions": len(v), "failures": fail_counts[k]}
                           for k, v in sorted(fail_shapes.items(), key=lambda kv: -len(kv[1]))[:n] if len(v) > 1],
        "instructions_read": [{"skill": k, "sessions": len(v), "reads": read_counts[k]}
                              for k, v in sorted(skill_reads.items(), key=lambda kv: -read_counts[kv[0]])[:n]],
        "residue": residue(args.repos, n),
        "automations": automations(Path(args.automations).expanduser(), n),
        "friction": friction(args.friction or args.repos, n) if args.friction is not None else None,
    }


def markdown(d) -> str:
    w = d["window"]
    out = [f"# Session digest ({w['since'] or 'all'} to {w['until'] or 'now'})", ""]
    out.append("Coverage: " + "; ".join(f"{h}: {v}" for h, v in d["coverage"].items()))
    t = d["totals"]
    out.append("Totals: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in t.items()))
    out += ["", "## Threads with the most user re-prompting", "",
            "| host | session | cwd | hours | user msgs | nudges | corrections | heartbeats | asks | compactions | failed cmds | worktrees | PRs |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in d["threads"]:
        out.append(f"| {f['host']} | {f['session'][-12:]} | {f['cwd'].replace(str(HOME), '~')} | {f['hours']} | {f['user_messages']} | "
                   f"{f['nudges']} | {f['corrections']} | {f['heartbeats']} | {f['asks_user']} | {f['compactions']} | "
                   f"{f['failed_commands']} | {f['worktrees_added']} | {f['prs_created']} |")
    out += ["", "## User corrections and nudges, with the agent message before each", ""]
    for s in d["signals"]:
        out.append(f"- {s['ts']} {s['host']} {s['session'][-12:]} ({s['kind']})")
        out.append(f"  - agent before: {tail(s['before'], 280) or '(none)'}")
        out.append(f"  - user: {mask(s['user'], 280)}")
    if d["failing_shapes"]:
        out += ["", "## Failing command shapes in more than one session", "", "| shape | sessions | failures |", "|---|---|---|"]
        out += [f"| `{r['shape']}` | {r['sessions']} | {r['failures']} |" for r in d["failing_shapes"]]
    if d["instructions_read"]:
        out += ["", "## Skill files read by agents", "", "| skill | sessions | reads |", "|---|---|---|"]
        out += [f"| {r['skill']} | {r['sessions']} | {r['reads']} |" for r in d["instructions_read"]]
    if d.get("automations"):
        out += ["", "## Agent-created automations", "", "| id | kind | status | schedule | age (days) | stop clause |", "|---|---|---|---|---|---|"]
        out += [f"| {a['id']} | {a['kind']} | {a['status']} | {a['schedule']} | {a['age_days']} | {a['stop_clause'] or '(none found)'} |"
                for a in d["automations"]]
    if d["residue"]:
        out += ["", "## Repository residue", "", "| repo | default | extra worktrees | local branches | merged but present | examples |",
                "|---|---|---|---|---|---|"]
        out += [f"| {r['repo'].replace(str(HOME), '~')} | {r['default']} | {r['extra_worktrees']} | {r['local_branches']} | "
                f"{r['merged_but_present']} | {', '.join(r['examples'])} |" for r in d["residue"]]
    fr = d.get("friction")
    if fr:
        out += ["", f"## Friction stores: {fr['stores']} stores, {fr['records']} records, {fr['clusters']} clusters, "
                f"{fr['single_sightings']} seen once", ""]
        out += [f"- {r['sightings']}x {r['key']} ({', '.join(r['repos'])}): {r['title']}" for r in fr["recurring"]]
    out += ["", "Read an incident in full with: digest.py show SESSION_ID --at TIMESTAMP"]
    return "\n".join(out) + "\n"


def show(args):
    target = None
    if args.file:
        paths = [Path(args.file)]
    else:
        paths = []
        for root, pattern in ((args.codex, f"*{args.session}*.jsonl"), (args.claude, f"*{args.session}*.jsonl"),
                              (args.gemini, f"chats/*{args.session[:8]}*.json")):
            if root and Path(root).is_dir():
                paths += sorted(Path(root).rglob(pattern))
    def reader_for(p):
        root = str(p)
        return read_gemini if p.suffix == ".json" else read_claude if "/.claude/" in root or args.claude in root else read_codex

    for p in paths:
        target = reader_for(p)(p)
        if target.timeline:
            break
    if (not target or not target.timeline) and not args.file:
        # the id may live only inside the log (session_meta or sessionId), not in its file name
        for root, pattern in ((args.codex, "*.jsonl"), (args.claude, "*.jsonl"), (args.gemini, "chats/*.json")):
            if root and Path(root).is_dir():
                for p in Path(root).rglob(pattern):
                    s = reader_for(p)(p)
                    if s.id == args.session and s.timeline:
                        target = s
                        break
            if target and target.timeline:
                break
    if not target or not target.timeline:
        print(f"error: session {args.session!r} not found under the given log directories\n"
              "hint: pass --codex/--claude/--gemini roots or --file PATH", file=sys.stderr)
        return 2
    items = target.timeline
    if args.at:
        at = stamp(args.at)
        idx = min(range(len(items)), key=lambda i: abs((stamp(items[i][0]) or at) - at), default=0)
        items = items[max(0, idx - args.context): idx + args.context + 1]
    print(f"# {target.host} {target.id} {target.cwd}")
    for ts, role, text in items:
        print(f"\n[{ts}] {role}: {mask(text, args.chars)}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", nargs="?", default="digest", choices=["digest", "show"])
    ap.add_argument("session", nargs="?")
    ap.add_argument("--since", default="7d")
    ap.add_argument("--until")
    ap.add_argument("--codex", default=str(HOME / ".codex/sessions"))
    ap.add_argument("--claude", default=str(HOME / ".claude/projects"))
    ap.add_argument("--gemini", default=str(HOME / ".gemini/tmp"))
    ap.add_argument("--repos", nargs="*", default=[str(HOME / "repos")])
    ap.add_argument("--automations", default=str(HOME / ".codex" / "automations"),
                    help="directory of agent-created automations (Codex: ~/.codex/automations)")
    ap.add_argument("--friction", nargs="*", default=None, help="roots holding .local*/reports/friction stores")
    ap.add_argument("--max-items", type=int, default=12)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--at")
    ap.add_argument("--context", type=int, default=6)
    ap.add_argument("--chars", type=int, default=1200)
    ap.add_argument("--file")
    args = ap.parse_args(argv)
    if args.command == "show":
        if not args.session and not args.file:
            print("error: show needs SESSION_ID or --file PATH\nhint: digest.py show 01a0e61d --at 2026-09-27T03:34", file=sys.stderr)
            return 2
        return show(args)
    d = build(args)
    sys.stdout.write(json.dumps(d, default=str, separators=(",", ":")) + "\n" if args.json else markdown(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
