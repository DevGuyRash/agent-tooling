"""The hidden repositories and cases for go-git-archive, built with the host's git: build(dest, git) makes them under
dest, the same every time (fixed authors, dates, and contents, so the same commit ids), and CASES lists each case's
repository, arguments, and expected outcome kind.

- tidewatch: export-ignore patterns (a directory, a ** pattern, a suffix), an export-subst file, an executable
  script, a symlink, files in subdirectories; release tags v0.9.0 (lightweight), v1.2.0, v1.9.0, v1.10.0
  (annotated), a pre-release v2.0.0-rc.1 and a nightly tag after them, and a commit after every tag. The working
  tree has an uncommitted change to a tracked file, an untracked file, and an ignored one, none of which belongs in
  a release tarball.
- harbor-bell: v0.1.0 and v0.2.0, and an ignored dist/ already holding a stale tarball for 0.2.0 and a SHA256SUMS
  whose lines are out of order and include a stale line for that tarball and one for another project.
- prerelease-only: only v3.0.0-beta.1 and a nightly tag.
- no-config: a repository without .shipkit.
"""
import os
import subprocess
from pathlib import Path

ENV_BASE = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "LANG": "C",
            "GIT_AUTHOR_NAME": "Mara Quist", "GIT_AUTHOR_EMAIL": "mara@tidewater.example",
            "GIT_COMMITTER_NAME": "Mara Quist", "GIT_COMMITTER_EMAIL": "mara@tidewater.example"}

# (name, repository, arguments, expected: "ok" or a fragment of standard error for an error)
CASES = [
    ("latest", "tidewatch", ["tarball"], "ok"),
    ("explicit-v", "tidewatch", ["tarball", "v1.2.0"], "ok"),
    ("lightweight-out-dir", "tidewatch", ["tarball", "-o", "out/release", "0.9.0"], "ok"),
    ("missing-tag", "tidewatch", ["tarball", "1.3.0"], "no tag v1.3.0"),
    ("bad-version", "tidewatch", ["tarball", "1.2"], "bad version 1.2"),
    ("pre-release", "tidewatch", ["tarball", "2.0.0-rc.1"], "bad version 2.0.0-rc.1"),
    ("replace-line", "harbor-bell", ["tarball"], "ok"),
    ("older-release", "harbor-bell", ["tarball", "0.1.0"], "ok"),
    ("no-release-tags", "prerelease-only", ["tarball"], "no release tags"),
    ("no-config", "no-config", ["tarball", "1.0.0"], "no .shipkit"),
]

VERSION_GO = 'package version\n\n// Commit and Date are filled in by git archive (export-subst).\nconst (\n\tCommit = "$Format:%H$"\n\tDate   = "$Format:%cs$"\n)\n'


class Repo:
    def __init__(self, path, git):
        self.path, self.git_bin = Path(path), git
        self.path.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args, when="2024-11-02T09:00:00Z"):
        env = dict(ENV_BASE, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
        return subprocess.run([self.git_bin, *args], cwd=self.path, env=env, check=True, capture_output=True,
                              timeout=60).stdout.decode()

    def write(self, rel, text, mode=0o644):
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        os.chmod(p, mode)

    def commit(self, message, when):
        self.git("add", "-A", when=when)
        self.git("commit", "-q", "-m", message, when=when)

    def tag(self, name, when, annotated=True):
        if annotated:
            self.git("tag", "-a", name, "-m", f"Release {name}", when=when)
        else:
            self.git("tag", name, when=when)


def tidewatch(dest, git):
    r = Repo(dest / "tidewatch", git)
    r.write(".shipkit", "# tidewatch\nname = tidewatch\n")
    r.write(".gitignore", ".env\n/dist/\n/out/\n")
    r.write(".gitattributes", "/.github export-ignore\n/testdata/** export-ignore\n*.psd export-ignore\n"
                              "internal/version/version.go export-subst\n")
    r.write("README.md", "# tidewatch\n\nTide tables for the Tidewater estuary.\n")
    r.write("LICENSE", "MIT License\n\nCopyright (c) 2024 Tidewater\n")
    os.symlink("LICENSE", r.path / "LICENSE.txt")
    r.write("go.mod", "module example.org/tidewatch\n\ngo 1.22\n")
    r.write("main.go", 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("tidewatch") }\n')
    r.write("internal/tide/tide.go", "package tide\n\n// Height is the tide height in centimetres.\ntype Height int\n")
    r.write("internal/version/version.go", VERSION_GO)
    r.write(".github/workflows/ci.yml", "on: push\njobs: {}\n")
    r.write("testdata/tides.csv", "time,height\n00:00,120\n")
    r.write("testdata/nested/deep.csv", "time,height\n")
    r.write("design/logo.psd", "8BPS fake\n")
    r.write("docs/USAGE.md", "Run `tidewatch`.\n")
    r.write("scripts/install.sh", "#!/bin/sh\nset -eu\ncp tidewatch /usr/local/bin\n", 0o755)
    r.commit("tidewatch: first tide tables", "2024-11-02T09:00:00Z")
    r.tag("v0.9.0", "2024-11-02T09:05:00Z", annotated=False)
    r.write("internal/tide/tide.go", "package tide\n\n// Height is the tide height in centimetres.\ntype Height int\n\n"
                                     "// Spring reports a spring tide.\nfunc Spring(h Height) bool { return h > 400 }\n")
    r.commit("spring tides", "2025-01-10T14:30:00Z")
    r.tag("v1.2.0", "2025-01-10T14:35:00Z")
    r.write("docs/USAGE.md", "Run `tidewatch` or `tidewatch -week`.\n")
    r.commit("a week at a time", "2025-03-05T11:00:00Z")
    r.tag("v1.9.0", "2025-03-05T11:10:00Z")
    r.write("main.go", 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("tidewatch 1.10") }\n')
    r.write("testdata/tides.csv", "time,height\n00:00,120\n06:00,410\n")
    r.commit("1.10: new banner", "2025-05-20T16:45:00Z")
    r.tag("v1.10.0", "2025-05-20T16:50:00Z")
    r.write("internal/tide/neap.go", "package tide\n\n// Neap reports a neap tide.\nfunc Neap(h Height) bool { return h < 150 }\n")
    r.commit("neap tides (2.0 preview)", "2025-06-01T10:00:00Z")
    r.tag("v2.0.0-rc.1", "2025-06-01T10:05:00Z")
    r.tag("nightly", "2025-06-01T10:06:00Z", annotated=False)
    r.write("README.md", "# tidewatch\n\nTide tables for the Tidewater estuary, now with neaps.\n")
    r.commit("readme: neaps", "2025-06-15T08:00:00Z")
    # The working tree is not a release: an edit, an untracked file, an ignored file.
    r.write("main.go", 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("tidewatch dev") }\n')
    r.write("NOTES-local.txt", "remember the 2026 tables\n")
    r.write(".env", "TIDE_STATION=dev\n")


def harbor_bell(dest, git):
    r = Repo(dest / "harbor-bell", git)
    r.write(".shipkit", "name = harbor-bell\n")
    r.write(".gitignore", "/dist/\n")
    r.write("bell.py", "print('ding')\n")
    r.write("README", "harbor-bell rings the harbour bell on the hour.\n")
    r.commit("harbor-bell", "2025-02-01T12:00:00Z")
    r.tag("v0.1.0", "2025-02-01T12:01:00Z")
    r.write("bell.py", "print('ding dong')\n")
    r.commit("two notes", "2025-04-12T07:30:00Z")
    r.tag("v0.2.0", "2025-04-12T07:31:00Z")
    r.write("dist/harbor-bell-0.2.0.tar.gz", "not the real tarball\n")
    r.write("dist/SHA256SUMS",
            f"{'0' * 64}  zz-other-1.0.tar.gz\n"
            f"{'f' * 64}  harbor-bell-0.2.0.tar.gz\n"
            f"{'a' * 64}  harbor-bell-0.1.0.tar.gz\n")


def prerelease_only(dest, git):
    r = Repo(dest / "prerelease-only", git)
    r.write(".shipkit", "name = quayside\n")
    r.write("quay.txt", "berths\n")
    r.commit("quayside", "2025-07-01T09:00:00Z")
    r.tag("v3.0.0-beta.1", "2025-07-01T09:01:00Z")
    r.tag("nightly", "2025-07-01T09:02:00Z", annotated=False)


def no_config(dest, git):
    r = Repo(dest / "no-config", git)
    r.write("README.md", "no shipkit here\n")
    r.commit("start", "2025-07-02T09:00:00Z")
    r.tag("v1.0.0", "2025-07-02T09:01:00Z")


def build(dest, git):
    dest = Path(dest)
    for make in (tidewatch, harbor_bell, prerelease_only, no_config):
        make(dest, git)
