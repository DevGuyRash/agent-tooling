"""Regenerate the hidden repositories and expected outputs for rs-git-summary.

Run from anywhere: python3 make_cases.py. It writes repos/NAME.fi (git fast-import streams the check loads
into fresh repositories), expected/CASE.out, and cases.json next to itself. Expected outputs are computed
here from the commit model, independently of git, following docs/repo-summary.md in the fixture. The
model is deterministic, so rebuilding gives the same bytes.

Properties the data relies on: history is linear (no merges), no commit deletes a file and adds another
with the same content (so rename detection never pairs paths), every change alters the file's content,
paths are ASCII, author times fall between 10:00 and 15:00 local time at offsets from -08:00 to +09:00
(so the author's local date and the UTC date agree), author dates never decrease along the history, and
no repository has a .mailmap. Where the committer differs from the author, the committer's name and date
differ too, so reading the committer instead of the author changes the output.
"""
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOT = ("Merge Bot", "bot@acme.example")


class Repo:
    def __init__(self, start):
        self.day = start  # a date
        self.commits = []
        self.tree = {}
        self.rev = 0

    def commit(self, author, email, offset_h, hour, message, changes=(), deletes=(), committer=None, days=1):
        """changes: paths added or modified; deletes: paths removed. The author date advances by `days`."""
        self.day += timedelta(days=days)
        tz = timezone(timedelta(hours=offset_h))
        when = datetime(self.day.year, self.day.month, self.day.day, hour, 17, 0, tzinfo=tz)
        self.rev += 1
        mods = []
        for p in changes:
            content = f"{p}: revision {self.rev}\n"
            assert self.tree.get(p) != content
            self.tree[p] = content
            mods.append((p, content))
        for p in deletes:
            assert p in self.tree, p
            del self.tree[p]
        cname, cemail = committer or (author, email)
        cwhen = when + (timedelta(days=2, hours=3) if committer else timedelta())
        self.commits.append({"author": author, "email": email, "when": when, "committer": cname,
                             "cemail": cemail, "cwhen": cwhen, "message": message, "mods": mods,
                             "deletes": list(deletes)})

    def fast_import(self):
        out = []
        for i, c in enumerate(self.commits, 1):
            def stamp(dt):
                off = dt.utcoffset()
                mins = int(off.total_seconds() // 60)
                sign = "+" if mins >= 0 else "-"
                return f"{int(dt.timestamp())} {sign}{abs(mins) // 60:02d}{abs(mins) % 60:02d}"
            msg = c["message"].encode() + b"\n"
            out.append(f"commit refs/heads/main\nmark :{i}\n"
                       f"author {c['author']} <{c['email']}> {stamp(c['when'])}\n"
                       f"committer {c['committer']} <{c['cemail']}> {stamp(c['cwhen'])}\n".encode())
            out.append(b"data %d\n" % len(msg) + msg)
            for p, content in c["mods"]:
                data = content.encode()
                out.append(f"M 100644 inline {p}\n".encode() + b"data %d\n" % len(data) + data)
            for p in c["deletes"]:
                out.append(f"D {p}\n".encode())
            out.append(b"\n")
        return b"".join(out)

    def summary(self, limit):
        authors = Counter(c["author"] for c in self.commits)
        dates = [c["when"].strftime("%Y-%m-%d") for c in self.commits]
        files = Counter(p for c in self.commits for p in {*(m[0] for m in c["mods"]), *c["deletes"]})

        def ranked(counter):
            items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].encode()))
            return [f"{v:>6}  {k}" for k, v in items[:limit]]
        lines = [f"commits: {len(self.commits)}", f"authors: {len(authors)}", f"first: {min(dates)}",
                 f"last: {max(dates)}", "top authors:", *ranked(authors), "top files:", *ranked(files)]
        return ("\n".join(lines) + "\n").encode()


def service():
    r = Repo(datetime(2025, 11, 2).date())
    ana, ana2 = ("Ana Lima", "ana@acme.example"), ("Ana Lima", "ana.lima@users.noreply.example")
    ben, chen = ("Ben Okafor", "ben@acme.example"), ("Chen Wei", "chen@acme.example")
    dana, zoe, adam = ("Dana Kim", "dana@acme.example"), ("Zoe Park", "zoe@acme.example"), ("adam li", "adam@acme.example")
    plan = [
        (ana, -3, 11, "Initial service skeleton",
         ["Cargo.toml", "Makefile", "README.md", "docs/release notes.md", "src/config.rs", "src/main.rs"], [], None),
        (ana, -3, 14, "Parse the listen address", ["src/config.rs", "src/main.rs"], [], None),
        (ben, 1, 10, "Add health endpoint", ["src/main.rs", "src/health.rs"], [], None),
        (ben, 1, 12, "Document the health endpoint", ["README.md"], [], BOT),
        (chen, 8, 13, "Add legacy import shim", ["src/legacy.rs", "src/main.rs"], [], None),
        (ana2, -3, 10, "Release notes for 0.1", ["docs/release notes.md"], [], None),
        (ben, 1, 15, "Bump version", ["Cargo.toml"], [], BOT),
        (dana, 9, 11, "CI workflow", [".github/workflows/ci.yml", "Makefile"], [], None),
        (ana, -3, 12, "Config from environment", ["src/config.rs", "src/main.rs"], [], None),
        (chen, 8, 10, "Retry the upstream call", ["src/main.rs", "src/retry.rs"], [], None),
        (zoe, -8, 15, "Fix typo in README", ["README.md"], [], None),
        (ben, 1, 11, "Trigger CI", [], [], None),
        (ana2, -3, 13, "Release notes for 0.2", ["docs/release notes.md", "Cargo.toml"], [], None),
        (adam, 5, 12, "Ops runbook", ["docs/ops.md"], [], None),
        (chen, 8, 14, "Remove the legacy shim", ["src/main.rs"], ["src/legacy.rs"], None),
        (ana, -3, 10, "Graceful shutdown", ["src/main.rs", "src/health.rs"], [], None),
        (ben, 1, 13, "Lint fixes", ["src/retry.rs", "src/config.rs"], [], BOT),
        (zoe, -8, 13, "Explain the retry policy", ["src/retry.rs"], [], None),
        (dana, 9, 14, "Cache cargo in CI", [".github/workflows/ci.yml"], [], None),
        (ana, -3, 11, "Structured logging", ["Cargo.toml", "src/main.rs"], [], None),
        (ben, 1, 10, "Health check timeout", ["src/health.rs"], [], None),
        (chen, 8, 12, "Retry budget", ["src/retry.rs"], [], None),
        (ana2, -3, 15, "Release notes for 0.3", ["docs/release notes.md"], [], None),
        (adam, 5, 14, "Runbook: rollbacks", ["docs/ops.md"], [], None),
        (ben, 1, 12, "Makefile release target", ["Makefile"], [], BOT),
        (ana, -3, 13, "Config validation", ["src/config.rs"], [], None),
        (zoe, -8, 10, "README: configuration", ["README.md"], [], None),
        (dana, 9, 12, "Release workflow", [".github/workflows/release.yml"], [], None),
        (chen, 8, 11, "Jitter retries", ["src/retry.rs", "src/main.rs"], [], None),
        (ben, 1, 14, "Bump version", ["Cargo.toml"], [], None),
        (ana, -3, 14, "Metrics endpoint", ["src/main.rs", "src/metrics.rs"], [], None),
        (adam, 5, 10, "Runbook: paging", ["docs/ops.md"], [], None),
        (ben, 1, 11, "Metrics docs", ["README.md"], [], None),
        (chen, 8, 15, "Retry metrics", ["src/metrics.rs"], [], None),
        (ana2, -3, 12, "Release notes for 0.4", ["docs/release notes.md"], [], None),
        (ben, 1, 13, "Release 0.4", ["Cargo.toml"], [], BOT),
    ]
    for (name, email), off, hour, msg, changes, deletes, committer in plan:
        r.commit(name, email, off, hour, msg, changes, deletes, committer, days=9)
    return r


def team():
    r = Repo(datetime(2026, 3, 1).date())
    people = [("Marta Diaz", "marta@acme.example", 5), ("bob", "bob@home.example", 5), ("Bob", "bob@acme.example", 4),
              ("Kofi Mensah", "kofi@acme.example", 3), ("Lena Vogel", "lena@acme.example", 3),
              ("Ravi Iyer", "ravi@acme.example", 2), ("Émile Roux", "emile@acme.example", 1),
              ("Yuki Sato", "yuki@acme.example", 1)]
    order = []
    while any(n for *_, n in people):
        for i, (name, email, n) in enumerate(people):
            if n:
                order.append((name, email))
                people[i] = (name, email, n - 1)
    files = ["src/lib.rs", "src/api.rs", "README.md", "src/db.rs", "CHANGELOG.md", "tests/api.rs", "src/API.md"]
    for i, (name, email) in enumerate(order):
        changes = [files[0]] if i == 0 else []
        changes += [files[i % len(files)], files[(i * 3 + 1) % len(files)]]
        changes = list(dict.fromkeys(changes))
        if i == 0:
            changes = files[:]
        r.commit(name, email, [-5, 0, 2, 9][i % 4], 10 + i % 6, f"Change {i + 1}", changes, [], None, days=3)
    return r


def tiny():
    r = Repo(datetime(2026, 9, 1).date())
    r.commit("dependabot[bot]", "bot@dependabot.example", 0, 12, "Initial commit", ["README.md", "Cargo.toml"])
    return r


def main():
    (HERE / "repos").mkdir(exist_ok=True)
    (HERE / "expected").mkdir(exist_ok=True)
    repos = {"service": service(), "team": team(), "tiny": tiny()}
    for name, repo in repos.items():
        (HERE / "repos" / f"{name}.fi").write_bytes(repo.fast_import())
    # cwd is relative to the directory holding the repositories; "plain" is a directory that is no repository.
    cases = [
        ("service", "service", [], "service", 5),
        ("service-top-2", "service", ["-n", "2"], "service", 2),
        ("service-by-path", ".", ["service"], "service", 5),
        ("service-by-path-top-12", "plain", ["-n", "12", "../service"], "service", 12),
        ("team-top-3", "team", ["-n", "3"], "team", 3),
        ("team-all", "team", ["-n", "10"], "team", 10),
        ("tiny", "tiny", [], "tiny", 5),
        ("tiny-zero", "tiny", ["-n", "0"], "tiny", 0),
        ("not-a-repo", "plain", [], None, None),
    ]
    listed = []
    for name, cwd, args, repo, limit in cases:
        out = repos[repo].summary(limit) if repo else b""
        (HERE / "expected" / f"{name}.out").write_bytes(out)
        listed.append({"name": name, "cwd": cwd, "args": args, "status": 0 if repo else 1})
    (HERE / "cases.json").write_text(json.dumps(listed, indent=1) + "\n")


if __name__ == "__main__":
    main()
