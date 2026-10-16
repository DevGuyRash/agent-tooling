"""What gather.py extracts from each host's native logs, faithfully and without interpretation."""
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gather.py"


def _load_gather():
    """Import gather.py as a module (by path, not via sys.path) for direct unit tests of its
    pure functions, alongside the subprocess-level integration tests below."""
    spec = importlib.util.spec_from_file_location("gather_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gather = _load_gather()

# Git in these tests reads neither the developer's global git configuration nor the system's.
# A global setting that signs every commit (through an agent that asks for approval, say) makes
# each commit in a temporary repository slow or failing, and nothing here depends on what such
# a configuration says; the temporary repositories get everything they need from the test.
GIT_ISOLATION = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *args):
    env = dict(os.environ)
    env.update(GIT_ISOLATION)
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, text=True, env=env)


def run_gather_script(args, extra_env=None):
    """gather.py as a command, the way an executor runs it."""
    env = dict(os.environ)
    env.pop("CODEX_HOME", None)
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.update(GIT_ISOLATION)
    if extra_env:
        env.update(extra_env)
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          encoding="utf-8", env=env)


def jl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def item(ts, it):
    return {"timestamp": ts, "type": "event_msg", "payload": {"type": "item_completed", "item": it}}


def text_blocks(t):
    return [{"type": "text", "text": t}]


class GatherTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.codex_root = self.root / "codex"
        self.claude_root = self.root / "claude"
        self.gemini_root = self.root / "gemini"
        self.out = self.root / "out"

        # --- Codex: a main session with a command, a compaction, an unknown top-level record,
        #     and an unknown item_completed item type; plus a subagent thread. ---
        jl(self.codex_root / "2026" / "09" / "28" / "rollout-a.jsonl", [
            {"timestamp": "2026-09-28T10:00:00Z", "type": "session_meta", "payload": {"id": "codex-a", "cwd": str(self.root / "repo")}},
            item("2026-09-28T10:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("Fix the build and open a PR")}),
            item("2026-09-28T10:01:00Z", {"type": "CommandExecution", "id": "2", "command": ["bash", "-lc", "pytest -q"],
                                          "cwd": str(self.root / "repo"), "status": "completed", "exit_code": 1,
                                          "aggregated_output": "FAILED test_x with token ghp_" + "a" * 30}),
            item("2026-09-28T10:02:00Z", {"type": "AgentMessage", "id": "3", "content": text_blocks("Consolidated into one PR.")}),
            {"timestamp": "2026-09-28T10:03:00Z", "type": "compacted", "payload": {"message": "summary"}},
            item("2026-09-28T10:04:00Z", {"type": "FutureItemType", "id": "4", "some_field": "x"}),
            {"timestamp": "2026-09-28T10:05:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {}}},
            {"timestamp": "2026-09-28T10:06:00Z", "type": "brand_new_top_level_record", "payload": {"x": 1}},
        ])
        jl(self.codex_root / "2026" / "09" / "28" / "rollout-sub.jsonl", [
            {"timestamp": "2026-09-28T10:00:00Z", "type": "session_meta",
             "payload": {"id": "codex-sub", "cwd": str(self.root / "repo"),
                         "source": {"subagent": {"thread_spawn": {"parent_thread_id": "codex-a"}}}}},
            item("2026-09-28T10:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("subtask")}),
        ])

        # --- Claude Code: a main session with a tool call/result, a compaction marker, and an
        #     unrecognized record type; plus a subagent transcript under subagents/. ---
        jl(self.claude_root / "proj" / "main.jsonl", [
            {"timestamp": "2026-09-28T10:00:00Z", "type": "user", "cwd": str(self.root / "repo"), "sessionId": "claude-a",
             "message": {"content": "Run the tests"}},
            {"timestamp": "2026-09-28T10:01:00Z", "type": "assistant", "sessionId": "claude-a",
             "message": {"content": [{"type": "text", "text": "Running them now."},
                                      {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest -q"}}]}},
            {"timestamp": "2026-09-28T10:01:05Z", "type": "user", "sessionId": "claude-a",
             "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "FAILED"}]}},
            {"timestamp": "2026-09-28T10:02:00Z", "type": "assistant", "sessionId": "claude-a",
             "message": {"content": [{"type": "text", "text": "Tests fail; fixing."}]}},
            {"timestamp": "2026-09-28T10:03:00Z", "type": "pr-link", "sessionId": "claude-a", "url": "https://example/pr/1"},
            {"timestamp": "2026-09-28T10:04:00Z", "type": "system", "sessionId": "claude-a", "subtype": "compact_boundary"},
        ])
        jl(self.claude_root / "proj" / "main" / "subagents" / "agent-1.jsonl", [
            {"timestamp": "2026-09-28T10:00:30Z", "type": "user", "isSidechain": True, "sessionId": "claude-sub",
             "cwd": str(self.root / "repo"), "message": {"content": "subtask"}},
            {"timestamp": "2026-09-28T10:00:45Z", "type": "assistant", "isSidechain": True, "sessionId": "claude-sub",
             "message": {"content": [{"type": "text", "text": "done"}]}},
        ])

        # --- Gemini CLI: a main chat with a tool call and an unrecognized message type, a
        #     sibling .project_root file for cwd, and a nested subagent chat. ---
        gem_dir = self.gemini_root / "hash1"
        (gem_dir / "chats").mkdir(parents=True)
        (gem_dir / ".project_root").write_text(str(self.root / "repo") + "\n")
        (gem_dir / "chats" / "session-2026-09-28T10-00-abc12345.json").write_text(json.dumps({
            "sessionId": "gem-1", "startTime": "2026-09-28T10:00:00Z", "lastUpdated": "2026-09-28T10:05:00Z",
            "messages": [
                {"type": "user", "content": "Build it", "timestamp": "2026-09-28T10:00:00Z"},
                {"type": "gemini", "content": "ok", "timestamp": "2026-09-28T10:01:00Z",
                 "toolCalls": [{"name": "run_shell_command", "args": {"command": "pytest -q"}, "status": "error", "result": "boom"}]},
                {"type": "future-message-kind", "content": "???", "timestamp": "2026-09-28T10:02:00Z"},
            ]}))
        (gem_dir / "chats" / "gem-1").mkdir()
        (gem_dir / "chats" / "gem-1" / "session-sub.json").write_text(json.dumps({
            "sessionId": "gem-sub", "messages": [{"type": "user", "content": "subtask", "timestamp": "2026-09-28T10:01:30Z"}]}))

        # --- A git workspace at the shared cwd: a stash and an extra worktree. ---
        self.repo = self.root / "repo"
        self.repo.mkdir()
        g = lambda *a: git(self.repo, *a)
        g("init", "-q", "-b", "main")
        (self.repo / "f").write_text("x")
        g("add", "f")
        g("-c", "user.name=a", "-c", "user.email=a@b", "commit", "-qm", "init")
        (self.repo / "f").write_text("y")
        g("-c", "user.name=a", "-c", "user.email=a@b", "stash", "push", "-m", "wip")
        g("branch", "done-feature")
        g("worktree", "add", "-q", str(self.root / "repo-wt"), "-b", "topic")

    def tearDown(self):
        # shutil.rmtree, not a "rm -rf" subprocess: the latter doesn't exist on Windows, and
        # this suite's own portability claim ("runs on any OS") should hold for its own tests.
        shutil.rmtree(self.root, ignore_errors=True)

    def run_gather_raw(self, out=None, extra_env=None, extra_args=(), since="2000-01-01"):
        """The uninspected CompletedProcess, for tests that check a non-zero exit or that omit
        --out on purpose."""
        args = []
        if since is not None:
            args += ["--since", since]
        if out is not None:
            args += ["--out", str(out)]
        args += list(extra_args)
        return run_gather_script(args, extra_env)

    def run_gather(self, out, extra_env=None, extra_args=()):
        r = self.run_gather_raw(out, extra_env=extra_env, extra_args=extra_args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def default_roots(self):
        return ["--root", f"codex={self.codex_root}", "--root", f"claude={self.claude_root}", "--root", f"gemini={self.gemini_root}"]

    def test_faithful_counts_and_no_dropped_records(self):
        out = self.out / "run1"
        self.run_gather(out, extra_args=self.default_roots())
        index = (out / "index.md").read_text()
        self.assertIn("codex-a", index)
        self.assertIn("claude-a", index)
        self.assertIn("gem-1", index)
        # main codex session: 1 user, 1 agent, 1 tool call (command execution)
        codex_main = (out / "sessions" / "codex-codex-a.md").read_text()
        self.assertEqual(codex_main.count("] user:"), 1)
        self.assertEqual(codex_main.count("] agent:"), 1)
        self.assertEqual(codex_main.count("] tool_call:"), 1)
        self.assertEqual(codex_main.count("] compaction:"), 1)
        # the unrecognized item type and unrecognized top-level type are noted, not dropped; no
        # rendered line sits between them (the telemetry record between them is skipped), so
        # they share one note line
        self.assertIn("FutureItemType", codex_main)
        self.assertIn("brand_new_top_level_record", codex_main)
        self.assertEqual(codex_main.count("] note:"), 1)
        # the skipped telemetry record produced no line of any kind
        self.assertNotIn("token_count", codex_main)

    def test_subagent_threads_are_included_and_flagged(self):
        out = self.out / "run2"
        self.run_gather(out, extra_args=self.default_roots())
        index = (out / "index.md").read_text()
        rows = {l.split("|")[2].strip(): l for l in index.splitlines() if l.startswith("| ")}
        self.assertIn("codex-sub", rows)
        self.assertIn("yes", rows["codex-sub"])
        self.assertIn("no", rows["codex-a"])
        self.assertIn("claude-sub", rows)
        self.assertIn("gem-sub", rows)
        for sub_id in ("codex-sub", "claude-sub", "gem-sub"):
            self.assertIn("yes", rows[sub_id])

    def test_unknown_claude_and_gemini_record_types_are_noted(self):
        out = self.out / "run3"
        self.run_gather(out, extra_args=self.default_roots())
        claude_main = (out / "sessions" / "claude-claude-a.md").read_text()
        self.assertIn("pr-link", claude_main)
        self.assertIn("] tool_call: Bash", claude_main)
        self.assertIn("] tool_result:", claude_main)
        self.assertIn("] compaction:", claude_main)
        gem_main = (out / "sessions" / "gemini-gem-1.md").read_text()
        self.assertIn("future-message-kind", gem_main)
        self.assertIn("] tool_call: run_shell_command", gem_main)

    def test_gemini_cwd_comes_from_project_root_file(self):
        out = self.out / "run4"
        self.run_gather(out, extra_args=self.default_roots())
        index = (out / "index.md").read_text()
        gem_row = next(l for l in index.splitlines() if "gem-1" in l and l.startswith("| gemini"))
        self.assertIn("repo", gem_row)

    def test_missing_host_is_noted_with_the_path_it_tried(self):
        out = self.out / "run5"
        missing = self.root / "no-such-claude-dir"
        self.run_gather(out, extra_args=["--root", f"codex={self.codex_root}", "--root", f"claude={missing}",
                                         "--root", f"gemini={self.gemini_root}"])
        index = (out / "index.md").read_text()
        self.assertIn(str(missing), index)
        self.assertIn("claude", index.split(str(missing))[0][-40:])

    def test_relocated_codex_home_via_environment_variable(self):
        codex_home = self.root / "alt-codex-home"
        jl(codex_home / "sessions" / "rollout-b.jsonl", [
            {"timestamp": "2026-09-28T11:00:00Z", "type": "session_meta", "payload": {"id": "codex-relocated", "cwd": "/tmp/x"}},
            item("2026-09-28T11:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("hi")}),
        ])
        auto_dir = codex_home / "automations" / "keepalive"
        auto_dir.mkdir(parents=True)
        (auto_dir / "automation.toml").write_text(
            'id = "keepalive"\nkind = "heartbeat"\nstatus = "ACTIVE"\nrrule = "RRULE:FREQ=HOURLY"\n'
            'created_at = 1790000000000\ntarget_thread_id = "abc"\n')
        out = self.out / "run6"
        self.run_gather(out, extra_env={"CODEX_HOME": str(codex_home)},
                         extra_args=["--root", f"claude={self.claude_root}", "--root", f"gemini={self.gemini_root}"])
        index = (out / "index.md").read_text()
        self.assertIn("codex-relocated", index)
        workspace = (out / "workspace.md").read_text()
        self.assertIn("keepalive", workspace)
        self.assertIn("ACTIVE", workspace)

    def test_masks_token_like_strings_in_transcripts(self):
        out = self.out / "run7"
        self.run_gather(out, extra_args=self.default_roots())
        codex_main = (out / "sessions" / "codex-codex-a.md").read_text()
        self.assertNotIn("ghp_" + "a" * 30, codex_main)
        self.assertIn("[masked]", codex_main)

    def test_git_workspace_reports_stash_and_extra_worktree_as_facts(self):
        out = self.out / "run8"
        self.run_gather(out, extra_args=self.default_roots())
        workspace = (out / "workspace.md").read_text()
        self.assertIn(str(self.repo).replace(str(Path.home()), "~") if str(self.repo).startswith(str(Path.home())) else str(self.repo),
                      workspace)
        self.assertIn("worktrees (1)", workspace)
        self.assertIn("stashes (1)", workspace)
        self.assertIn("done-feature", workspace)  # a merged, non-default branch is listed as a fact
        # "topic" (checked out in the extra worktree) is merged too; git marks it "+ topic" in
        # `branch --merged`, and only the branch name, not that marker, belongs in the fact.
        self.assertIn("topic", workspace)
        self.assertNotIn("+ topic", workspace)

    def test_empty_content_records_are_noted_not_silently_dropped(self):
        # A "user"/"assistant" (Claude) or a message (Gemini) with blank content and no tool
        # calls has nothing to render as a user/agent/tool_call/tool_result line; it must still
        # leave a trace, not vanish. (Codex's UserMessage/AgentMessage items always carry
        # through whatever text they have, even empty, so it is not exercised here.)
        claude_empty = self.root / "claude-empty"
        jl(claude_empty / "proj" / "empty.jsonl", [
            {"timestamp": "2026-09-28T09:00:00Z", "type": "user", "sessionId": "claude-empty", "message": {"content": ""}},
        ])
        gem_empty_dir = self.root / "gemini-empty" / "hash2"
        (gem_empty_dir / "chats").mkdir(parents=True)
        (gem_empty_dir / "chats" / "session-empty.json").write_text(json.dumps(
            {"sessionId": "gem-empty", "messages": [{"type": "gemini", "content": "", "timestamp": "2026-09-28T09:00:00Z"}]}))
        out = self.out / "run10"
        self.run_gather(out, extra_args=["--root", f"codex={self.codex_root}", "--root", f"claude={claude_empty}",
                                         "--root", f"gemini={self.root / 'gemini-empty'}"])
        for name in ("claude-claude-empty.md", "gemini-gem-empty.md"):
            content = (out / "sessions" / name).read_text()
            self.assertIn("had no renderable content", content, name)

    def test_prints_output_directory_and_counts(self):
        out = self.out / "run9"
        stdout = self.run_gather(out, extra_args=self.default_roots())
        self.assertIn(str(out), stdout)
        self.assertIn("sessions:", stdout)

    # ---- transcripts no longer silently overwrite each other -----------------------------

    def test_claude_subagent_sharing_parents_session_id_gets_its_own_transcript(self):
        # The real shape: a Claude subagent record carries the *parent's* sessionId, not a
        # sessionId of its own -- its only unique key is agentId (which the real file name,
        # agent-<agentId>.jsonl, also carries). Two such subagents plus their parent must
        # produce three distinct, non-overwriting transcript files.
        root = self.root / "claude-collide"
        jl(root / "proj" / "main.jsonl", [
            {"timestamp": "2026-09-28T10:00:00Z", "type": "user", "sessionId": "parent-1",
             "message": {"content": "parent task"}},
        ])
        jl(root / "proj" / "main" / "subagents" / "agent-aaa.jsonl", [
            {"timestamp": "2026-09-28T10:00:30Z", "type": "user", "sessionId": "parent-1", "agentId": "aaa",
             "isSidechain": True, "message": {"content": "subtask one"}},
        ])
        jl(root / "proj" / "main" / "subagents" / "agent-bbb.jsonl", [
            {"timestamp": "2026-09-28T10:00:45Z", "type": "user", "sessionId": "parent-1", "agentId": "bbb",
             "isSidechain": True, "message": {"content": "subtask two"}},
        ])
        out = self.out / "run-claude-collide"
        self.run_gather(out, extra_args=["--root", f"codex={self.codex_root}", "--root", f"claude={root}",
                                          "--root", f"gemini={self.gemini_root}"])
        index = (out / "index.md").read_text()
        rows = [l for l in index.splitlines() if l.startswith("| claude ")]
        self.assertEqual(len(rows), 3, index)
        # Every row's own readable link must resolve to a file that actually exists...
        session_files = set()
        for row in rows:
            cols = [c.strip() for c in row.split("|")]
            link = cols[13]  # "[sessions/....md](sessions/....md)"
            name = link.split("](")[0].lstrip("[")
            self.assertTrue((out / name).is_file(), f"missing {name}\n{index}")
            session_files.add(name)
        # ...and no two rows may point at the same file (the overwrite this finding reported).
        self.assertEqual(len(session_files), 3, session_files)
        # Each subtask's own text survives somewhere, rather than being lost to an overwrite.
        all_text = "\n".join((out / n).read_text() for n in session_files)
        self.assertIn("subtask one", all_text)
        self.assertIn("subtask two", all_text)
        self.assertIn("parent task", all_text)

    def test_two_codex_rollouts_sharing_one_session_meta_id_both_survive(self):
        codex_root = self.root / "codex-collide"
        jl(codex_root / "2026" / "01" / "01" / "rollout-a.jsonl", [
            {"timestamp": "2026-01-01T00:00:00Z", "type": "session_meta", "payload": {"id": "shared-id", "cwd": "/tmp/a"}},
            item("2026-01-01T00:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("first rollout content")}),
        ])
        jl(codex_root / "2026" / "01" / "02" / "rollout-b.jsonl", [
            {"timestamp": "2026-01-02T00:00:00Z", "type": "session_meta", "payload": {"id": "shared-id", "cwd": "/tmp/b"}},
            item("2026-01-02T00:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("second rollout content")}),
        ])
        out = self.out / "run-codex-collide"
        self.run_gather(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.gemini_root}"])
        index = (out / "index.md").read_text()
        rows = [l for l in index.splitlines() if l.startswith("| codex ") and "shared-id" in l]
        self.assertEqual(len(rows), 2, index)
        names = set()
        for row in rows:
            cols = [c.strip() for c in row.split("|")]
            link = cols[13]
            name = link.split("](")[0].lstrip("[")
            names.add(name)
        self.assertEqual(len(names), 2, names)  # not collapsed onto one file
        all_text = "\n".join((out / n).read_text() for n in names)
        self.assertIn("first rollout content", all_text)
        self.assertIn("second rollout content", all_text)

    # ---- the current Gemini CLI's .jsonl chat format ---------------------------------------

    def test_gemini_jsonl_append_log_with_set_and_rewind(self):
        gem_dir = self.root / "gemini-jsonl" / "hashA"
        (gem_dir / "chats").mkdir(parents=True)
        (gem_dir / ".project_root").write_text(str(self.repo) + "\n")
        lines = [
            {"sessionId": "gem-jsonl-1", "projectHash": "hashA", "startTime": "2026-09-29T00:00:00Z"},
            {"id": "m1", "type": "user", "content": "first question", "timestamp": "2026-09-29T00:00:01Z"},
            {"id": "m2", "type": "gemini", "content": "an answer that will be rewound",
             "timestamp": "2026-09-29T00:00:02Z"},
            {"$rewindTo": "m2"},
            {"id": "m2", "type": "gemini", "content": "the real answer", "timestamp": "2026-09-29T00:00:03Z",
             "toolCalls": [{"name": "run_shell_command", "args": {"command": "ls"}, "status": "ok", "result": "f"}]},
            {"$set": {"lastUpdated": "2026-09-29T00:00:04Z"}},
        ]
        (gem_dir / "chats" / "session-2026-09-29T00-00-abcdef01.jsonl").write_text(
            "\n".join(json.dumps(r) for r in lines) + "\n")
        out = self.out / "run-gemini-jsonl"
        self.run_gather(out, extra_args=["--root", f"codex={self.codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.root / 'gemini-jsonl'}"])
        index = (out / "index.md").read_text()
        self.assertIn("gem-jsonl-1", index)
        row = next(l for l in index.splitlines() if "gem-jsonl-1" in l and l.startswith("| gemini"))
        self.assertIn(str(self.repo).replace(str(Path.home()), "~") if str(self.repo).startswith(str(Path.home()))
                      else "repo", row)
        transcript = (out / "sessions" / "gemini-gem-jsonl-1.md").read_text()
        self.assertIn("first question", transcript)
        self.assertIn("the real answer", transcript)
        self.assertNotIn("rewound", transcript)  # $rewindTo removed the superseded m2
        self.assertIn("run_shell_command", transcript)

    def test_gemini_jsonl_subagent_chat_is_discovered_and_flagged(self):
        gem_dir = self.root / "gemini-jsonl-sub" / "hashB"
        (gem_dir / "chats" / "gem-parent-1").mkdir(parents=True)
        (gem_dir / "chats" / "session-2026-09-29T00-05-11112222.jsonl").write_text(
            json.dumps({"sessionId": "gem-parent-1", "startTime": "2026-09-29T00:05:00Z"}) + "\n" +
            json.dumps({"id": "p1", "type": "user", "content": "top task", "timestamp": "2026-09-29T00:05:01Z"}) + "\n")
        (gem_dir / "chats" / "gem-parent-1" / "gem-sub-1.jsonl").write_text(
            json.dumps({"sessionId": "gem-sub-1", "startTime": "2026-09-29T00:05:30Z"}) + "\n" +
            json.dumps({"id": "s1", "type": "user", "content": "sub task", "timestamp": "2026-09-29T00:05:31Z"}) + "\n")
        out = self.out / "run-gemini-jsonl-sub"
        self.run_gather(out, extra_args=["--root", f"codex={self.codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.root / 'gemini-jsonl-sub'}"])
        index = (out / "index.md").read_text()
        rows = {l.split("|")[2].strip(): l for l in index.splitlines() if l.startswith("| gemini")}
        self.assertIn("gem-parent-1", rows)
        self.assertIn("gem-sub-1", rows)
        self.assertIn("no", rows["gem-parent-1"].split("|")[10])  # subagent column, not archived
        self.assertIn("yes", rows["gem-sub-1"])

    # ---- Codex archived_sessions is read, not silently skipped -----------------------------

    def test_codex_archived_sessions_are_read_and_marked(self):
        codex_root = self.root / "codex-arch" / "sessions"
        jl(codex_root / "2026" / "01" / "01" / "rollout-active.jsonl", [
            {"timestamp": "2026-01-01T00:00:00Z", "type": "session_meta", "payload": {"id": "active-1", "cwd": "/tmp"}},
            item("2026-01-01T00:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("active")}),
        ])
        archived_root = self.root / "codex-arch" / "archived_sessions"
        jl(archived_root / "rollout-old.jsonl", [
            {"timestamp": "2020-01-01T00:00:00Z", "type": "session_meta", "payload": {"id": "archived-1", "cwd": "/tmp"}},
            item("2020-01-01T00:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("archived")}),
        ])
        out = self.out / "run-codex-archived"
        self.run_gather(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.gemini_root}"])
        index = (out / "index.md").read_text()
        self.assertIn("archived-1", index)
        self.assertIn("codex archived: root", index)
        row = next(l for l in index.splitlines() if "archived-1" in l and l.startswith("| codex"))
        self.assertIn("yes", row.split("|")[11])  # the archived column
        active_row = next(l for l in index.splitlines() if "active-1" in l and l.startswith("| codex"))
        self.assertIn("no", active_row.split("|")[11])

    # ---- Codex response_item content is counted, not silently skipped ----------------------

    def test_codex_response_item_records_are_aggregated_not_silently_skipped(self):
        # This custom_tool_call/-output pair shares its call_id ("c1") with a CommandExecution
        # item elsewhere in the file, so it has a genuine twin (the old-format case) and stays
        # aggregated rather than individually rendered -- contrast with
        # test_codex_custom_tool_call_renders_commands_when_no_command_execution_items below,
        # where no CommandExecution id matches the call_id and that flips to a full render.
        codex_root = self.root / "codex-response-item"
        jl(codex_root / "rollout.jsonl", [
            {"timestamp": "2026-01-01T00:00:00Z", "type": "session_meta", "payload": {"id": "ri-1", "cwd": "/tmp"}},
            item("2026-01-01T00:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("hello")}),
            item("2026-01-01T00:00:02Z", {"type": "CommandExecution", "id": "c1", "command": ["true"],
                                          "cwd": "/tmp", "exit_code": 0}),
            {"timestamp": "2026-01-01T00:00:03Z", "type": "response_item",
             "payload": {"type": "custom_tool_call", "name": "exec", "call_id": "c1"}},
            {"timestamp": "2026-01-01T00:00:04Z", "type": "response_item",
             "payload": {"type": "custom_tool_call_output", "call_id": "c1"}},
            {"timestamp": "2026-01-01T00:00:05Z", "type": "response_item",
             "payload": {"type": "agent_message", "author": "a", "recipient": "b"}},
        ])
        out = self.out / "run-response-item"
        self.run_gather(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.gemini_root}"])
        transcript = (out / "sessions" / "codex-ri-1.md").read_text()
        # Not rendered as full entries (redundant with item_completed's own rendering when a
        # twin exists) -- but not invisible either: an aggregated note names each type and count.
        self.assertIn("response_item/custom_tool_call:", transcript)
        self.assertIn("response_item/custom_tool_call_output:", transcript)
        self.assertIn("response_item/agent_message:", transcript)
        self.assertIn(str(codex_root / "rollout.jsonl"), transcript)  # points back at the raw file

    # ---- newer rollout format: exec calls with no CommandExecution twin anywhere -----------

    def test_codex_custom_tool_call_renders_commands_when_no_command_execution_items(self):
        # A newer Codex rollout format routes every command through response_item's own
        # custom_tool_call/custom_tool_call_output payloads, with no item_completed/
        # CommandExecution item anywhere in the file. The "input" is a freeform code snippet
        # (synthetic shape based on a survey of real 2026-08/2026-09 rollouts on this machine;
        # no real session content is copied here) -- the actual command text lives inside it.
        codex_root = self.root / "codex-unified-exec"
        jl(codex_root / "rollout.jsonl", [
            {"timestamp": "2026-08-23T10:00:00Z", "type": "session_meta", "payload": {"id": "exec-1", "cwd": "/tmp"}},
            item("2026-08-23T10:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("list files")}),
            {"timestamp": "2026-08-23T10:00:02Z", "type": "response_item",
             "payload": {"type": "custom_tool_call", "id": "rec1", "call_id": "call_1", "name": "exec",
                         "input": 'const r = await tools.exec_command({"cmd":"ls -la /tmp"}); text(r.output);'}},
            {"timestamp": "2026-08-23T10:00:03Z", "type": "response_item",
             "payload": {"type": "custom_tool_call_output", "id": "rec2", "call_id": "call_1",
                         "output": [{"type": "input_text", "text": "total 0\ndrwx------ 2 u u 40 Jan 1 00:00 ."}]}},
            {"timestamp": "2026-08-23T10:00:04Z", "type": "response_item",
             "payload": {"type": "custom_tool_call", "id": "rec3", "call_id": "call_2", "name": "exec",
                         "input": 'const r = await tools.exec_command({"cmd":"curl -H \'Authorization: '
                                  'Bearer sk-ant-' + "a" * 20 + '\' https://api.example/x"});'}},
            item("2026-08-23T10:00:05Z", {"type": "AgentMessage", "id": "3", "content": text_blocks("done")}),
        ])
        out = self.out / "run-unified-exec"
        self.run_gather(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.gemini_root}"])
        transcript = (out / "sessions" / "codex-exec-1.md").read_text()
        self.assertIn("ls -la /tmp", transcript)
        self.assertIn("] tool_call: exec(exec):", transcript)
        self.assertIn("] tool_result: exec result:", transcript)
        self.assertIn("total 0", transcript)
        # The second command's embedded secret is masked like any other transcript text.
        self.assertNotIn("sk-ant-" + "a" * 20, transcript)
        self.assertIn("[masked]", transcript)
        # No longer folded into the "not individually rendered" aggregate note.
        self.assertNotIn("response_item/custom_tool_call:", transcript)
        self.assertNotIn("response_item/custom_tool_call_output:", transcript)

    def test_codex_mixed_rollout_renders_only_the_custom_tool_calls_without_a_twin(self):
        # Real rollouts on this machine are commonly *mixed*, not purely old- or new-format: a
        # handful of item_completed/CommandExecution items share a call's exact id (a genuine
        # twin, e.g. an older in-process exec path) while most custom_tool_call records in the
        # very same file have no CommandExecution anywhere with a matching id (an unrelated
        # CommandExecution elsewhere in the file -- e.g. automatic startup housekeeping -- must
        # not make those look redundant too). The correlation is per call_id, not "this rollout
        # has a CommandExecution item somewhere" (synthetic shape based on a survey of real
        # rollouts; no real session content is copied here).
        codex_root = self.root / "codex-mixed"
        jl(codex_root / "rollout.jsonl", [
            {"timestamp": "2026-09-01T10:00:00Z", "type": "session_meta", "payload": {"id": "mixed-1", "cwd": "/tmp"}},
            item("2026-09-01T10:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("do two things")}),
            # An unrelated startup-housekeeping CommandExecution: its id never matches any
            # custom_tool_call's call_id in this file.
            item("2026-09-01T10:00:02Z", {"type": "CommandExecution", "id": "exec-startup-aaa",
                                          "command": ["cat", "AGENTS.md"], "cwd": "/tmp", "exit_code": 0,
                                          "source": "unified_exec_startup"}),
            # A genuine twin: this CommandExecution's id matches call_twinned's call_id exactly.
            item("2026-09-01T10:00:03Z", {"type": "CommandExecution", "id": "call_twinned",
                                          "command": ["echo", "twinned"], "cwd": "/tmp", "exit_code": 0}),
            {"timestamp": "2026-09-01T10:00:04Z", "type": "response_item",
             "payload": {"type": "custom_tool_call", "call_id": "call_twinned", "name": "exec",
                         "input": 'const r = await tools.exec_command({"cmd":"echo twinned"});'}},
            {"timestamp": "2026-09-01T10:00:05Z", "type": "response_item",
             "payload": {"type": "custom_tool_call_output", "call_id": "call_twinned",
                         "output": [{"type": "input_text", "text": "twinned"}]}},
            # No twin anywhere in the file: must render in full even though CommandExecution
            # items exist elsewhere in this same rollout.
            {"timestamp": "2026-09-01T10:00:06Z", "type": "response_item",
             "payload": {"type": "custom_tool_call", "call_id": "call_untwinned", "name": "exec",
                         "input": 'const r = await tools.exec_command({"cmd":"echo untwinned-command"});'}},
            {"timestamp": "2026-09-01T10:00:07Z", "type": "response_item",
             "payload": {"type": "custom_tool_call_output", "call_id": "call_untwinned",
                         "output": [{"type": "input_text", "text": "untwinned"}]}},
        ])
        out = self.out / "run-mixed"
        self.run_gather(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.gemini_root}"])
        transcript = (out / "sessions" / "codex-mixed-1.md").read_text()
        # The untwinned command is rendered in full -- this is the one a whole-file
        # "has any CommandExecution" check would have wrongly hidden.
        self.assertIn("echo untwinned-command", transcript)
        self.assertIn("untwinned", transcript)
        # The twinned command is NOT individually re-rendered from its custom_tool_call record
        # (it is already visible via the CommandExecution item's own "$ echo twinned" line).
        self.assertIn("$ echo twinned", transcript)
        self.assertNotIn("echo twinned});", transcript)  # the raw custom_tool_call "input" text
        self.assertIn("response_item/custom_tool_call: 1 record(s)", transcript)
        self.assertIn("response_item/custom_tool_call_output: 1 record(s)", transcript)

    # ---- newer rollout format: built-in extension tools as item_completed/Extension -------

    def test_codex_extension_items_render_as_tool_calls(self):
        # Another part of the newer rollout format: built-in tools like a sleep/delay or a web
        # search show up as a terse item_completed/Extension marker (kind, id, and type-specific
        # fields) instead of a recognized item type like WebSearch (synthetic shape based on a
        # survey of real 2026-09 rollouts; no real session content is copied here).
        codex_root = self.root / "codex-extension"
        jl(codex_root / "rollout.jsonl", [
            {"timestamp": "2026-09-08T10:00:00Z", "type": "session_meta", "payload": {"id": "ext-1", "cwd": "/tmp"}},
            item("2026-09-08T10:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("wait then search")}),
            item("2026-09-08T10:00:02Z", {"type": "Extension", "kind": "clock.sleep", "id": "call_1",
                                          "durationMs": 30000}),
            item("2026-09-08T10:00:03Z", {"type": "Extension", "kind": "web.search", "id": "call_2",
                                          "query": "agent skills spec", "action": {"type": "search"},
                                          "results": [{"title": "Agent Skills", "url": "https://example/agent-skills"}]}),
        ])
        out = self.out / "run-extension"
        self.run_gather(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.gemini_root}"])
        transcript = (out / "sessions" / "codex-ext-1.md").read_text()
        self.assertIn("] tool_call: extension clock.sleep", transcript)
        self.assertIn("durationMs", transcript)
        self.assertIn("] tool_call: extension web.search", transcript)
        self.assertIn("agent skills spec", transcript)
        self.assertNotIn("item_completed/Extension", transcript)

    # ---- the classic structured tool-call channel: function_call/function_call_output ------

    def test_codex_function_call_renders_when_no_command_execution_twin(self):
        # function_call is the older structured tool-call channel (name + a JSON "arguments"
        # string) that coexists with the newer custom_tool_call channel; it has the same gap --
        # no item_completed twin means the command is otherwise invisible (synthetic shape based
        # on a survey of real rollouts on this machine; no real session content is copied here).
        codex_root = self.root / "codex-function-call"
        jl(codex_root / "rollout.jsonl", [
            {"timestamp": "2026-04-01T10:00:00Z", "type": "session_meta", "payload": {"id": "fc-1", "cwd": "/tmp"}},
            item("2026-04-01T10:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("list files")}),
            {"timestamp": "2026-04-01T10:00:02Z", "type": "response_item",
             "payload": {"type": "function_call", "name": "exec_command", "call_id": "call_untwinned",
                         "arguments": '{"cmd":"ls -la /tmp"}'}},
            {"timestamp": "2026-04-01T10:00:03Z", "type": "response_item",
             "payload": {"type": "function_call_output", "call_id": "call_untwinned", "output": "total 0"}},
        ])
        out = self.out / "run-function-call"
        self.run_gather(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.gemini_root}"])
        transcript = (out / "sessions" / "codex-fc-1.md").read_text()
        self.assertIn("exec_command({\"cmd\":\"ls -la /tmp\"})", transcript)
        self.assertIn("] tool_call: exec_command(", transcript)
        self.assertIn("] tool_result: call result: total 0", transcript)
        self.assertNotIn("response_item/function_call:", transcript)
        self.assertNotIn("response_item/function_call_output:", transcript)

    def test_codex_function_call_stays_aggregated_when_a_command_execution_twin_exists(self):
        # Mirrors test_codex_response_item_records_are_aggregated_not_silently_skipped for the
        # function_call channel: a genuine CommandExecution twin (matching call_id) means the
        # command is already visible via that item, so the response_item stays aggregated.
        codex_root = self.root / "codex-function-call-twinned"
        jl(codex_root / "rollout.jsonl", [
            {"timestamp": "2026-04-01T10:00:00Z", "type": "session_meta", "payload": {"id": "fc-2", "cwd": "/tmp"}},
            item("2026-04-01T10:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("hello")}),
            item("2026-04-01T10:00:02Z", {"type": "CommandExecution", "id": "call_twinned", "command": ["true"],
                                          "cwd": "/tmp", "exit_code": 0}),
            {"timestamp": "2026-04-01T10:00:03Z", "type": "response_item",
             "payload": {"type": "function_call", "name": "exec_command", "call_id": "call_twinned",
                         "arguments": '{"cmd":"true"}'}},
            {"timestamp": "2026-04-01T10:00:04Z", "type": "response_item",
             "payload": {"type": "function_call_output", "call_id": "call_twinned", "output": ""}},
        ])
        out = self.out / "run-function-call-twinned"
        self.run_gather(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.gemini_root}"])
        transcript = (out / "sessions" / "codex-fc-2.md").read_text()
        self.assertIn("$ true", transcript)  # rendered once, via the CommandExecution item
        self.assertIn("response_item/function_call: 1 record(s)", transcript)
        self.assertIn("response_item/function_call_output: 1 record(s)", transcript)

    # ---- web_search_call: no call_id/id at all, so it always renders in full ---------------

    def test_codex_web_search_call_always_renders(self):
        # web_search_call carries no call_id/id on this machine's rollouts, so it can never
        # match a CommandExecution item -- it must always render, unconditionally (synthetic
        # shape based on a survey of real rollouts; no real session content is copied here).
        codex_root = self.root / "codex-web-search-call"
        jl(codex_root / "rollout.jsonl", [
            {"timestamp": "2026-05-01T10:00:00Z", "type": "session_meta", "payload": {"id": "wsc-1", "cwd": "/tmp"}},
            item("2026-05-01T10:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("search something")}),
            {"timestamp": "2026-05-01T10:00:02Z", "type": "response_item",
             "payload": {"type": "web_search_call", "status": "completed",
                         "action": {"type": "search", "query": "agent skills spec", "queries": ["agent skills spec"]}}},
        ])
        out = self.out / "run-web-search-call"
        self.run_gather(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={self.claude_root}",
                                          "--root", f"gemini={self.gemini_root}"])
        transcript = (out / "sessions" / "codex-wsc-1.md").read_text()
        self.assertIn("] tool_call: web_search_call:", transcript)
        self.assertIn("agent skills spec", transcript)
        self.assertNotIn("response_item/web_search_call:", transcript)

    # ---- one malformed record no longer sinks the whole run --------------------------------

    def test_malformed_records_are_noted_not_fatal(self):
        codex_root = self.root / "codex-bad"
        jl(codex_root / "bad.jsonl", [
            {"timestamp": "2026-01-01T00:00:00Z", "type": "session_meta", "payload": {"id": 12345, "cwd": ["not", "a", "string"]}},
            [],  # a non-object top-level record
            {"timestamp": "2026-01-01T00:00:02Z", "type": "response_item", "payload": "not-an-object"},
            item("2026-01-01T00:00:03Z", {"type": "UserMessage", "id": "1", "content": text_blocks("still readable")}),
        ])
        claude_root = self.root / "claude-bad"
        jl(claude_root / "proj" / "bad.jsonl", [
            {"timestamp": "2026-01-01T00:00:00Z", "type": "user", "sessionId": "claude-bad-1", "cwd": ["not", "a", "string"],
             "message": "not-an-object"},
            {"timestamp": "2026-01-01T00:00:01Z", "type": "assistant", "sessionId": "claude-bad-1",
             "message": {"content": [{"type": "text", "text": None}]}},
            {"timestamp": "2026-01-01T00:00:02Z", "type": "assistant", "sessionId": "claude-bad-1",
             "message": {"content": [{"type": "text", "text": "still readable too"}]}},
        ])
        gemini_root = self.root / "gemini-bad"
        gd = gemini_root / "hashbad"
        (gd / "chats").mkdir(parents=True)
        (gd / "chats" / "session-bad-list.json").write_text(json.dumps(["not", "an", "object"]))
        (gd / "chats" / "session-bad-messages.json").write_text(json.dumps(
            {"sessionId": "gem-bad-1", "messages": {"not": "a list"}}))
        (gd / "chats" / "session-bad-toolcalls.json").write_text(json.dumps(
            {"sessionId": "gem-bad-2", "messages": [
                {"type": "gemini", "content": "ok", "timestamp": "2026-01-01T00:00:00Z", "toolCalls": ["not-an-object"]}]}))
        out = self.out / "run-malformed"
        r = self.run_gather_raw(out, extra_args=["--root", f"codex={codex_root}", "--root", f"claude={claude_root}",
                                                  "--root", f"gemini={gemini_root}"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((out / "index.md").is_file())
        all_transcripts = "\n".join(p.read_text() for p in (out / "sessions").glob("*.md"))
        self.assertIn("still readable", all_transcripts)
        self.assertIn("still readable too", all_transcripts)

    # ---- UTF-8, regardless of the process locale --------------------------------------------

    def test_survives_non_utf8_locale_and_preserves_unicode_text(self):
        root = self.root / "claude-unicode"
        jl(root / "proj" / "main.jsonl", [
            {"timestamp": "2026-01-01T00:00:00Z", "type": "user", "sessionId": "unicode-1",
             "message": {"content": "café → ✓ 日本語"}},
        ])
        out = self.out / "run-unicode"
        env = {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
        r = self.run_gather_raw(out, extra_env=env,
                                 extra_args=["--root", f"codex={self.codex_root}", "--root", f"claude={root}",
                                             "--root", f"gemini={self.gemini_root}"])
        self.assertEqual(r.returncode, 0, r.stderr)
        transcript = next((out / "sessions").glob("claude-unicode-1*.md")).read_text(encoding="utf-8")
        self.assertIn("café", transcript)
        self.assertIn("日本語", transcript)

    # ---- output-directory privacy and rerun safety ------------------------------------------

    def test_default_out_is_a_private_temp_directory_not_the_cwd(self):
        cwd_before = set(os.listdir(self.root))
        r = self.run_gather_raw(out=None, extra_args=["--root", f"codex={self.codex_root}",
                                                        "--root", f"claude={self.claude_root}",
                                                        "--root", f"gemini={self.gemini_root}"])
        try:
            self.assertEqual(r.returncode, 0, r.stderr)
            m = [l for l in r.stdout.splitlines() if l.startswith("wrote ")]
            self.assertTrue(m, r.stdout)
            written = Path(m[0][len("wrote "):])
            self.assertNotEqual(written.parent, Path.cwd())
            self.assertTrue(written.is_dir())
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(written.stat().st_mode), 0o700)
        finally:
            if 'written' in dir() and Path(written).is_dir():
                shutil.rmtree(written, ignore_errors=True)
        # gather.py must not have written anything into the (unrelated) cwd it ran with.
        self.assertEqual(set(os.listdir(self.root)), cwd_before)

    def test_refuses_nonempty_out_without_force(self):
        out = self.out / "run-refuse"
        out.mkdir(parents=True)
        (out / "stray-file.txt").write_text("pre-existing")
        r = self.run_gather_raw(out, extra_args=self.default_roots())
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("error:", r.stderr)
        self.assertFalse((out / "index.md").exists())
        self.assertTrue((out / "stray-file.txt").exists())  # untouched
        # --force allows writing into it anyway.
        r2 = self.run_gather_raw(out, extra_args=list(self.default_roots()) + ["--force"])
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertTrue((out / "index.md").exists())

    # ---- git-missing is reported, not disguised as "no repository found" -------------------

    def test_missing_git_binary_is_reported_explicitly(self):
        out = self.out / "run-no-git"
        empty_path_dir = self.root / "empty-path"
        empty_path_dir.mkdir()
        env = dict(os.environ)
        env.pop("CODEX_HOME", None)
        env.pop("CLAUDE_CONFIG_DIR", None)
        # An empty directory as the whole PATH: no git, no crontab/systemctl either. sys.executable
        # is an absolute path, so launching Python itself doesn't depend on PATH resolution.
        env["PATH"] = str(empty_path_dir)
        args = [sys.executable, str(SCRIPT), "--since", "2000-01-01", "--out", str(out)] + list(self.default_roots())
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        workspace = (out / "workspace.md").read_text()
        self.assertIn("git was not found on PATH", workspace)
        self.assertNotIn("No session recorded a working directory", workspace)


# ---------------------------------------------------------------------------- shared fixtures

UTC = dt.timezone.utc


def hours_ago(hours):
    return (dt.datetime.now(UTC) - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


class LogHome(unittest.TestCase):
    """A temporary set of per-host log roots to put synthetic logs in and run gather.py over."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.roots = {host: self.root / host for host in ("codex", "claude", "gemini")}
        for path in self.roots.values():
            path.mkdir()
        self.runs = 0

    def gather(self, since="2000-01-01", extra=()):
        self.runs += 1
        out = self.root / f"out{self.runs}"
        args = ["--since", since, "--out", str(out)]
        for host, path in self.roots.items():
            args += ["--root", f"{host}={path}"]
        r = run_gather_script(args + list(extra))
        self.assertEqual(r.returncode, 0, r.stderr)
        return out

    def session_ids(self, out):
        rows = [l for l in (out / "index.md").read_text(encoding="utf-8").splitlines()
                if l.startswith("| ") and not l.startswith(("| host", "|---"))]
        return {row.split("|")[2].strip() for row in rows}

    def index_row(self, out, session_id):
        return next(l for l in (out / "index.md").read_text(encoding="utf-8").splitlines()
                    if l.startswith("| ") and l.split("|")[2].strip() == session_id)

    def transcript(self, out, host, session_id):
        return (out / "sessions" / f"{host}-{session_id}.md").read_text(encoding="utf-8")


CLOCK = dt.datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)


def at(n):
    """The n-th second of the fixtures' clock, as a log record carries it."""
    return (CLOCK + dt.timedelta(seconds=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def shown(n):
    """The same instant as a transcript line shows it."""
    return (CLOCK + dt.timedelta(seconds=n)).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------- the time window

class WindowTest(LogHome):
    """A session is in the window by its own records' timestamps, not by when its file was last
    written."""

    def claude_session(self, name, session_id, stamps):
        jl(self.roots["claude"] / "proj" / f"{name}.jsonl", [
            {"timestamp": t, "type": "user", "sessionId": session_id, "cwd": "/srv/agent-fixture",
             "message": {"content": f"message {i}"}} for i, t in enumerate(stamps)])

    def test_a_file_written_today_whose_records_are_old_is_not_in_a_recent_window(self):
        # Every file below was just written, so its modification time is "now" for all of them.
        self.claude_session("old", "claude-old", ["2020-01-01T00:00:00Z", "2020-01-01T00:05:00Z"])
        self.claude_session("fresh", "claude-fresh", [hours_ago(3), hours_ago(2)])
        self.claude_session("spanning", "claude-spanning", [hours_ago(24 * 10), hours_ago(1)])
        out = self.gather(since="1d")
        self.assertEqual(self.session_ids(out), {"claude-fresh", "claude-spanning"})
        # A session that straddles --since is kept whole, its old record included.
        self.assertIn("message 0", self.transcript(out, "claude", "claude-spanning"))

    def test_until_selects_by_the_day_a_session_began_not_by_its_file(self):
        self.claude_session("old", "claude-old", ["2020-01-01T00:00:00Z", "2020-01-01T00:05:00Z"])
        self.claude_session("fresh", "claude-fresh", [hours_ago(3), hours_ago(2)])
        self.claude_session("spanning", "claude-spanning", [hours_ago(24 * 10), hours_ago(1)])
        out = self.gather(since="2000-01-01", extra=["--until", "2020-01-01"])
        self.assertEqual(self.session_ids(out), {"claude-old"})

    def test_until_ends_at_the_midnight_after_its_date_and_a_session_at_that_midnight_is_out(self):
        self.claude_session("last-second", "claude-last-second", ["2020-01-01T23:59:59Z"])
        self.claude_session("midnight", "claude-midnight", ["2020-01-02T00:00:00Z"])
        for name, stamped in (("in", dt.datetime(2020, 1, 1, 23, 59, 59, tzinfo=UTC)),
                              ("out", dt.datetime(2020, 1, 2, tzinfo=UTC))):
            raw = self.roots["claude"] / "proj" / f"untimed-{name}.jsonl"
            jl(raw, [{"type": "user", "sessionId": f"claude-untimed-{name}", "message": {"content": "hello"}}])
            os.utime(raw, (stamped.timestamp(), stamped.timestamp()))  # no record timestamps: the file's time decides
        out = self.gather(since="2000-01-01", extra=["--until", "2020-01-01"])
        self.assertEqual(self.session_ids(out), {"claude-last-second", "claude-untimed-in"})

    def test_a_session_without_record_timestamps_is_placed_by_its_files_modification_time(self):
        for name in ("stale", "recent"):
            jl(self.roots["claude"] / "proj" / f"{name}.jsonl", [
                {"type": "user", "sessionId": f"claude-untimed-{name}", "message": {"content": "hello"}}])
        month_ago = dt.datetime.now(UTC).timestamp() - 30 * 86400
        os.utime(self.roots["claude"] / "proj" / "stale.jsonl", (month_ago, month_ago))
        out = self.gather(since="1d")
        self.assertEqual(self.session_ids(out), {"claude-untimed-recent"})

    def test_a_file_stamped_hours_earlier_than_the_record_in_it_is_still_read(self):
        # A log synced from a machine whose clock ran behind: the file system stamped the file 12 hours
        # before --since, yet the newest record in it is inside the window.
        raw = self.roots["claude"] / "proj" / "skewed.jsonl"
        jl(raw, [{"timestamp": hours_ago(23), "type": "user", "sessionId": "claude-skewed", "message": {"content": "hi"}}])
        stamped = dt.datetime.now(UTC).timestamp() - 36 * 3600
        os.utime(raw, (stamped, stamped))
        self.assertEqual(self.session_ids(self.gather(since="1d")), {"claude-skewed"})

    def test_a_record_the_transcript_does_not_show_still_counts_as_the_sessions_latest(self):
        # token_count telemetry is not rendered, but it is a record of the session, and the latest.
        stamp = hours_ago(1)
        jl(self.roots["codex"] / "rollout-telemetry.jsonl", [
            {"timestamp": "2020-01-01T00:00:00Z", "type": "session_meta",
             "payload": {"id": "codex-telemetry", "cwd": "/srv/agent-fixture"}},
            item("2020-01-01T00:00:01Z", {"type": "UserMessage", "id": "1", "content": text_blocks("hello")}),
            {"timestamp": stamp, "type": "event_msg", "payload": {"type": "token_count", "info": {}}}])
        out = self.gather(since="1d")
        self.assertEqual(self.session_ids(out), {"codex-telemetry"})
        self.assertEqual(self.index_row(out, "codex-telemetry").split("|")[5].strip(),
                         dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).isoformat())  # "end"

    def test_codex_and_gemini_sessions_are_placed_by_their_records_too(self):
        for name, stamp in (("old", "2020-01-01T00:00:00Z"), ("fresh", hours_ago(2))):
            jl(self.roots["codex"] / f"rollout-{name}.jsonl", [
                {"timestamp": stamp, "type": "session_meta", "payload": {"id": f"codex-{name}", "cwd": "/srv/agent-fixture"}},
                item(stamp, {"type": "UserMessage", "id": "1", "content": text_blocks("hello")})])
            chats = self.roots["gemini"] / f"hash-{name}" / "chats"
            chats.mkdir(parents=True)
            (chats / f"session-{name}.json").write_text(json.dumps({
                "sessionId": f"gem-{name}", "startTime": stamp, "lastUpdated": stamp,
                "messages": [{"type": "user", "content": "hello", "timestamp": stamp}]}))
        out = self.gather(since="1d")
        self.assertEqual(self.session_ids(out), {"codex-fresh", "gem-fresh"})


class WindowRuleTest(unittest.TestCase):
    """The edges of the window rule, where an off-by-one would quietly lose or admit a session."""

    def session(self, start, end):
        s = gather.Session("claude", Path("raw.jsonl"))
        s.start, s.end = start, end
        return s

    def test_latest_record_at_since_is_in_and_a_second_earlier_is_out(self):
        since = dt.datetime(2026, 1, 3, 10, 0, 0, tzinfo=UTC)
        one_second = dt.timedelta(seconds=1)
        early = dt.datetime(2026, 1, 1, tzinfo=UTC)
        self.assertTrue(gather.session_in_window(self.session(early, since), since, None))
        self.assertFalse(gather.session_in_window(self.session(early, since - one_second), since, None))

    def test_earliest_record_anywhere_in_the_until_day_is_in_and_the_midnight_after_it_is_out(self):
        until = gather.parse_when("2026-01-01")  # midnight UTC; the whole day is meant
        one_second = dt.timedelta(seconds=1)
        end = dt.datetime(2026, 2, 1, tzinfo=UTC)
        midnight_after = dt.datetime(2026, 1, 2, tzinfo=UTC)
        self.assertTrue(gather.session_in_window(self.session(until, end), None, until))
        self.assertTrue(gather.session_in_window(self.session(midnight_after - one_second, end), None, until))
        self.assertFalse(gather.session_in_window(self.session(midnight_after, end), None, until))
        self.assertFalse(gather.session_in_window(self.session(midnight_after + one_second, end), None, until))

    def test_no_bounds_admit_everything(self):
        s = self.session(dt.datetime(2000, 1, 1, tzinfo=UTC), dt.datetime(2000, 1, 2, tzinfo=UTC))
        self.assertTrue(gather.session_in_window(s, None, None))

    def test_without_timestamps_the_file_modification_time_decides(self):
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        raw = tmp / "raw.jsonl"
        raw.write_text("{}\n")
        stamp = dt.datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
        os.utime(raw, (stamp.timestamp(), stamp.timestamp()))
        s = gather.Session("claude", raw)
        self.assertIsNone(s.start)
        self.assertTrue(gather.session_in_window(s, stamp - dt.timedelta(days=1), stamp + dt.timedelta(days=1)))
        self.assertFalse(gather.session_in_window(s, stamp + dt.timedelta(days=1), None))
        self.assertFalse(gather.session_in_window(s, None, stamp - dt.timedelta(days=2)))

    def test_without_timestamps_a_file_stamped_at_the_midnight_after_the_until_day_is_out(self):
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        raw = tmp / "raw.jsonl"
        raw.write_text("{}\n")
        s = gather.Session("claude", raw)
        until = gather.parse_when("2026-01-01")
        midnight_after = dt.datetime(2026, 1, 2, tzinfo=UTC)
        os.utime(raw, (midnight_after.timestamp() - 1, midnight_after.timestamp() - 1))
        self.assertTrue(gather.session_in_window(s, None, until))
        os.utime(raw, (midnight_after.timestamp(), midnight_after.timestamp()))
        self.assertFalse(gather.session_in_window(s, None, until))

    def test_the_modification_time_prefilter_never_excludes_a_file_that_could_hold_a_record_in_the_window(self):
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        raw = tmp / "raw.jsonl"
        raw.write_text("{}\n")
        stamp = dt.datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
        os.utime(raw, (stamp.timestamp(), stamp.timestamp()))
        self.assertTrue(gather.could_hold_window(raw, None))
        self.assertTrue(gather.could_hold_window(raw, stamp - dt.timedelta(hours=1)))
        # A file may be stamped earlier than a record in it, by up to a day of clock difference.
        self.assertTrue(gather.could_hold_window(raw, stamp + dt.timedelta(seconds=30)))
        self.assertTrue(gather.could_hold_window(raw, stamp + dt.timedelta(hours=23)))
        self.assertFalse(gather.could_hold_window(raw, stamp + dt.timedelta(hours=25)))
        self.assertFalse(gather.could_hold_window(tmp / "missing.jsonl", None))


# ---------------------------------------------------------------------------- masking, everywhere

class MaskedEverywhereTest(LogHome):
    """Nothing gather.py writes carries a credential that a log or a configuration holds: not a
    transcript line, not a header, not a cell of the index, not a fact of the workspace file, and not
    a file name. Every value that reaches a file is masked, whichever code composed it."""

    def setUp(self):
        super().setUp()
        self.token = "ghp_" + "a" * 30           # assembled at run time: nothing secret-shaped is committed
        self.random = "Zk9mQ2vDzX7bR4sT1pL8n" * 2  # 42 characters with no prefix: only the catch-all finds it
        self.mixed = f"{self.token}-{self.random}"  # both, joined: the writer's by-shape pass finds only the first
        self.secrets = (self.token, self.random, "hunter22")
        # The working directory is a repository whose own name, branch, and stash carry the credential.
        self.repo = self.root / f"repo-{self.mixed}"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "f").write_text("x")
        git(self.repo, "add", "f")
        git(self.repo, "-c", "user.name=a", "-c", "user.email=a@b", "commit", "-qm", "init")
        git(self.repo, "branch", self.mixed)
        (self.repo / "f").write_text("y")
        git(self.repo, "-c", "user.name=a", "-c", "user.email=a@b", "stash", "push", "-m", f"wip {self.mixed}")
        # Claude Code: the session's id, its agent's id, a hook whose every field is a token, and JSON-shaped credentials.
        def record(kind, **fields):
            return {"timestamp": at(0), "type": kind, "sessionId": f"claude-{self.random}", "agentId": self.random,
                    "cwd": str(self.repo), **fields}
        self.claude_raw = self.roots["claude"] / "proj" / "plain-session.jsonl"
        jl(self.claude_raw, [
            record("user", message={"content": 'set {"password": "hunter22"} please'}),
            record("attachment", attachment={"type": "hook_non_blocking_error", "hookName": f"Stop-{self.mixed}",
                                             "hookEvent": f"Stop-{self.mixed}", "exitCode": self.mixed, "timedOut": True,
                                             "timeoutMs": self.mixed, "stderr": '{"password": "hunter22"}'}),
            record("assistant", message={"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                       "input": {"command": "curl -d '{\"password\": \"hunter22\"}' http://x"}}]}),
            record("user", message={"content": [{"type": "tool_result", "tool_use_id": self.mixed, "content": '{"password": "hunter22"}'}]})])
        # Codex: its own session id, and an automation whose every field is a token.
        codex_home = self.root / "codex-home"
        self.roots["codex"] = codex_home / "sessions"
        jl(self.roots["codex"] / "rollout-a.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": f"codex-{self.random}", "cwd": str(self.repo)}},
            item(at(1), {"type": "UserMessage", "id": "1", "content": text_blocks("hello")})])
        automation = codex_home / "automations" / "nightly"
        automation.mkdir(parents=True)
        fields = {k: self.mixed for k in ("id", "kind", "status", "rrule", "target_thread_id")}
        (automation / "automation.toml").write_text("".join(f'{k} = "{v}"\n' for k, v in fields.items()))
        # Gemini: a chat whose id is a token.
        chats = self.roots["gemini"] / "hash" / "chats"
        chats.mkdir(parents=True)
        (chats / "session-a.json").write_text(json.dumps({"sessionId": f"gem-{self.random}", "startTime": at(0), "lastUpdated": at(1),
                                                          "messages": [{"type": "user", "content": "hi", "timestamp": at(0)}]}))
        self.out = self.gather()

    def written(self, out=None):
        out = out or self.out
        return [(p, p.read_text(encoding="utf-8")) for p in sorted(out.rglob("*")) if p.is_file()]

    def assert_nothing_leaks(self, out=None):
        files = self.written(out)
        self.assertTrue(files)
        for path, text in files:
            for secret in self.secrets:
                self.assertNotIn(secret, text, f"{path.name} holds {secret[:8]}...")
                self.assertNotIn(secret, path.name)

    def test_no_file_or_file_name_holds_a_credential(self):
        self.assert_nothing_leaks()

    def test_every_field_of_a_hook_line_is_masked_and_the_line_is_still_there(self):
        transcripts = [t for p, t in self.written() if p.parent.name == "sessions" and p.name.startswith("claude-")]
        hook = next(l for t in transcripts for l in t.splitlines() if "] hook: " in l)
        # Each credential in a field becomes a [masked] marker (two, where a prefixed token and a prefixless one sit together).
        m = r"(?:\[masked\])+"
        self.assertRegex(hook, rf"\] hook: Stop-{m} failed \(non-blocking\) \(exit={m}, timed out after {m}ms\)")

    def test_headers_and_index_cells_are_masked_but_the_pointers_in_them_still_work(self):
        index = (self.out / "index.md").read_text(encoding="utf-8")
        for row in (l for l in index.splitlines() if l.startswith("| claude")):
            link = row.split("|")[13].strip()
            self.assertTrue((self.out / link.split("](")[1].rstrip(")")).is_file(), link)  # the readable link resolves
        # A raw log whose name is long and mixed (like a UUID) is a pointer, not a secret: it is not masked.
        plain = self.root / "claude2" / "proj" / "rollout-2026-10-15T09-11-58-01a14055-5d49-7033-a5ee-9c4a77e02fa2.jsonl"
        jl(plain, [{"timestamp": at(0), "type": "user", "sessionId": "claude-plain", "message": {"content": "hi"}}])
        out = self.root / "pointer-run"
        r = run_gather_script(["--since", "2000-01-01", "--out", str(out), "--root", f"claude={self.root / 'claude2'}",
                               "--root", f"codex={self.root / 'none'}", "--root", f"gemini={self.root / 'none'}"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"raw log: {plain}  ", (out / "sessions" / "claude-claude-plain.md").read_text(encoding="utf-8"))
        self.assertIn(f"| {plain} |", (out / "index.md").read_text(encoding="utf-8"))

    def test_the_workspace_facts_are_masked(self):
        workspace = (self.out / "workspace.md").read_text(encoding="utf-8")
        self.assertIn("## ", workspace)                    # the repository's facts are there...
        m = r"(?:\[masked\])+"
        self.assertRegex(workspace, rf"automation `{m}`: kind={m}, status={m}, schedule={m}, thread={m}")
        self.assertIn("stashes (1): ", workspace)         # ...and so is the stash, with its token masked
        self.assertNotIn(self.token, workspace)

    def test_a_credential_in_what_is_missing_is_masked_in_the_index_and_in_what_is_printed(self):
        missing = self.root / f"no-such-{self.mixed}"
        out = self.root / "coverage-run"
        r = run_gather_script(["--since", "2000-01-01", "--out", str(out), "--root", f"claude={self.roots['claude']}",
                               "--root", f"codex={self.roots['codex']}", "--root", f"gemini={missing}"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gemini: not found, tried ", (out / "index.md").read_text(encoding="utf-8"))
        self.assertNotIn(self.token, r.stdout)
        self.assert_nothing_leaks(out)


# ---------------------------------------------------------------------------- pointers are masked too

class PointerMaskingTest(LogHome):
    """The path of a raw log, the references in a transcript, and the path cells of the index are
    masked like any other value: a directory named like a token does not reach a file. What a pointer
    is made of -- UUIDs, hex ids and SHAs, dates and times, a host's encoded-cwd directory name --
    stays readable, so the pointer still works, unless it holds a token-shaped run of its own."""

    HALF = "Zk9mQ2vDzX7bR4sT1pL8n"       # 21 characters: not token-shaped alone, so it can only vanish with its run
    RANDOM = HALF * 2                     # 42 characters, no prefix: only the catch-all finds it

    def log(self, path, session_id):
        jl(path, [{"timestamp": at(0), "type": "user", "sessionId": session_id, "message": {"content": "hello"}},
                  {"timestamp": at(1), "type": "assistant", "sessionId": session_id,
                   "message": {"content": [{"type": "text", "text": "x" * 60}]}}])
        return path

    def setUp(self):
        super().setUp()
        claude = self.roots["claude"]
        # Directories named like a token: whole, as the tail of an encoded cwd, and as two words joined by a hyphen.
        self.token_dirs = [self.log(claude / self.RANDOM / "a.jsonl", "claude-a"),
                           self.log(claude / f"-home-user-{self.RANDOM}" / "b.jsonl", "claude-b"),
                           self.log(claude / f"{self.HALF}-{self.HALF}" / "c.jsonl", "claude-c"),
                           self.log(claude / f"{'0199abcd-ef01-7234-8bcd-0123456789ab'}-{self.RANDOM}" / "d.jsonl", "claude-d")]
        # Pointers as the hosts make them: all long, all mixed, none a secret.
        encoded = "-home-user-agent-tooling--claude-worktrees-heal-gather-2026-q3-roadmap"
        self.pointers = [
            self.log(claude / encoded / "0199abcd-ef01-7234-8bcd-0123456789ab.jsonl", "claude-uuid"),
            self.log(claude / encoded / "0199abcd-ef01-7234-8bcd-0123456789ab" / "subagents" / "agent-a1b2c3d4e5f6a7b8.jsonl", "claude-sub"),
        ]
        rollout = self.roots["codex"] / "2026" / "10" / "15" / "rollout-2026-10-15T09-11-58-01a14055-5d49-7033-a5ee-9c4a77e02fa2.jsonl"
        jl(rollout, [{"timestamp": at(0), "type": "session_meta", "payload": {"id": "codex-rollout", "cwd": "/srv/x"}},
                     item(at(1), {"type": "UserMessage", "id": "1", "content": text_blocks("hello")})])
        self.pointers.append(rollout)
        sha = "a1b2c3d4" * 8                 # a project hash: 64 hex characters
        chat = self.roots["gemini"] / sha / "chats"
        chat.mkdir(parents=True)
        (chat / "session-2026-10-15T10-00-abc12345.json").write_text(json.dumps({
            "sessionId": "gem-pointer", "startTime": at(0), "lastUpdated": at(1),
            "messages": [{"type": "user", "content": "hello", "timestamp": at(0)}]}))
        self.pointers.append(chat / "session-2026-10-15T10-00-abc12345.json")
        self.out = self.gather()

    def written(self):
        return [(p, p.read_text(encoding="utf-8")) for p in sorted(self.out.rglob("*")) if p.is_file()]

    def test_no_file_holds_a_directory_named_like_a_token(self):
        files = self.written()
        self.assertTrue(files)
        for path, text in files:
            self.assertNotIn(self.HALF, text, path.name)
            self.assertNotIn(self.HALF, path.name)

    def test_the_header_the_references_and_the_index_cell_say_where_the_mask_is(self):
        claude = self.roots["claude"]
        text = self.transcript(self.out, "claude", "claude-a")
        index = (self.out / "index.md").read_text(encoding="utf-8")
        self.assertIn(f"raw log: {claude}/[masked]/a.jsonl  ", text)
        self.assertIn(f"] user: hello  ({claude}/[masked]/a.jsonl:1)", text)
        self.assertIn(f"| {claude}/[masked]/a.jsonl |", index)
        # An encoded cwd that ends in a token is masked as a whole; a UUID beside a token goes with it.
        self.assertIn(f"| {claude}/[masked]/b.jsonl |", index)
        self.assertIn(f"| {claude}/[masked]/c.jsonl |", index)
        self.assertIn(f"| {claude}/[masked]/d.jsonl |", index)

    def test_the_pointers_hosts_make_still_point(self):
        index = (self.out / "index.md").read_text(encoding="utf-8")
        for path in self.pointers:
            self.assertIn(f"| {path} |", index)
        claude, sub, codex, gemini = self.pointers[0], self.pointers[1], self.pointers[2], self.pointers[3]
        for host, session_id, path, ref in (("claude", "claude-uuid", claude, f"{claude}:1"), ("codex", "codex-rollout", codex, f"{codex}:2"),
                                            ("gemini", "gem-pointer", gemini, f"{gemini}#msg0")):
            text = self.transcript(self.out, host, session_id)
            self.assertIn(f"raw log: {path}  ", text)
            self.assertIn(f"({ref})", text)

    def test_a_trimmed_text_names_the_raw_log_it_was_cut_from_without_the_token(self):
        jl(self.roots["claude"] / self.RANDOM / "long.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "claude-long", "message": {"content": "word " * 1000}}])
        out = self.gather(extra=["--max-chars", "100"])
        text = self.transcript(out, "claude", "claude-long")
        self.assertIn(f"[trimmed; full text at {self.roots['claude']}/[masked]/long.jsonl:1]", text)
        self.assertNotIn(self.HALF, text)

    def test_the_coverage_lines_mask_a_root_named_like_a_token_as_well(self):
        root = self.root / self.RANDOM
        self.log(root / "proj" / "r.jsonl", "claude-root")
        out = self.root / "root-run"
        r = run_gather_script(["--since", "2000-01-01", "--out", str(out), "--root", f"claude={root}",
                               "--root", f"codex={self.root / 'none'}", "--root", f"gemini={self.root / 'none'}"])
        self.assertEqual(r.returncode, 0, r.stderr)
        for path in sorted(out.rglob("*")):
            if path.is_file():
                self.assertNotIn(self.HALF, path.read_text(encoding="utf-8"), path.name)
        self.assertIn(f"- claude: root {self.root}/[masked]", (out / "index.md").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------- a quoted credential, whole

class QuotedCredentialTest(LogHome):
    """A credential in quotes is masked to the quote that closes it: a passphrase of several words does
    not survive as its second word, whichever host's record carried it, in whichever field."""

    WORDS = ("passphrase", "horse", "battery", "staple", "violet", "kettle")

    def setUp(self):
        super().setUp()
        short, long_, spoken = "short passphrase", "correct horse battery staple", "quiet violet kettle"
        # Claude Code: a user's words, a tool call's input (an object), a tool result, a hook's stderr.
        jl(self.roots["claude"] / "proj" / "s.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "claude-q", "message": {"content": f'use {{"password": "{short}"}} now'}},
            {"timestamp": at(1), "type": "assistant", "sessionId": "claude-q", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "login", "password": long_}}]}},
            {"timestamp": at(2), "type": "user", "sessionId": "claude-q", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": f'{{"secret": "{spoken}"}}'}]}},
            {"timestamp": at(3), "type": "attachment", "sessionId": "claude-q", "attachment": {
                "type": "hook_non_blocking_error", "hookName": "Stop", "hookEvent": "Stop", "exitCode": 1,
                "stderr": f"token = '{long_}'"}}])
        # Codex: a function call whose arguments are JSON holding a shell command that holds JSON.
        arguments = json.dumps({"cmd": f"curl -d '{json.dumps({'password': short})}' http://localhost"})
        jl(self.roots["codex"] / "rollout-q.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": "codex-q", "cwd": "/srv/q"}},
            item(at(1), {"type": "UserMessage", "id": "1", "content": text_blocks(f'password: "{spoken}"')}),
            {"timestamp": at(2), "type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                                                    "call_id": "c1", "arguments": arguments}}])
        # Gemini: a tool call's arguments (an object) and its result.
        chats = self.roots["gemini"] / "hash" / "chats"
        chats.mkdir(parents=True)
        (chats / "session-q.json").write_text(json.dumps({"sessionId": "gem-q", "startTime": at(0), "lastUpdated": at(1), "messages": [
            {"type": "gemini", "content": "ok", "timestamp": at(1),
             "toolCalls": [{"name": "login", "args": {"api_key": spoken}, "status": "ok", "result": f"password='{long_}'"}]}]}))
        self.out = self.gather()

    def test_no_word_of_any_credential_reaches_any_file(self):
        for path in sorted(self.out.rglob("*")):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for word in self.WORDS:
                    self.assertNotIn(word, text, f"{path.name} holds {word!r}")

    def test_the_lines_are_still_there_with_a_marker_where_the_credential_was(self):
        claude = self.transcript(self.out, "claude", "claude-q")
        self.assertIn('] user: use {"[masked]"} now  ', claude)
        self.assertRegex(claude, r'\] tool_call: .*"command": "login", "\[masked\]"')
        self.assertIn("] hook: Stop failed (non-blocking) (exit=1); stderr: [masked]'  ", claude)
        self.assertIn('] user: [masked]"  ', self.transcript(self.out, "codex", "codex-q"))

    def test_the_writer_masks_a_quoted_credential_in_a_name_no_field_masker_saw(self):
        if os.name == "nt":
            self.skipTest("a quote and a colon cannot be in a file name here")
        # The raw log's own path reaches the files only through the writer.
        jl(self.roots["claude"] / 'proj-password: "short passphrase"' / "named.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "claude-named", "message": {"content": "hi"}}])
        out = self.gather()
        for path in sorted(out.rglob("*")):
            if path.is_file():
                self.assertNotIn("passphrase", path.read_text(encoding="utf-8"), path.name)


# ---------------------------------------------------------------------------- no record aborts a run

class NoRecordAbortsTest(LogHome):
    """A log is data, and some of it will be odd: valid JSON that decodes to a lone surrogate, a
    number of thousands of digits, a nesting deeper than the stack. None of it may abort a run or cost
    a file its good records."""

    DEEP = "[" * 100000                        # a RecursionError for the JSON decoder
    HUGE = '{"type": "user", "sessionId": "x", "big": ' + "1" * 5000 + ', "message": {"content": "big number"}}'
    # (a ValueError on Python 3.11 and later; a record like any other before that)

    def raw_lines(self, path, lines):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n")

    def test_a_lone_surrogate_in_any_field_is_written_as_text_not_raised(self):
        # json.dumps writes the surrogate as the escape \ud800, which is valid JSON and decodes to a lone one.
        jl(self.roots["claude"] / "proj" / "s.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "claude-\ud800", "cwd": "/srv/x-\ud800",
             "message": {"content": "hello \ud800 there"}},
            {"timestamp": at(1), "type": "future-\ud800", "sessionId": "claude-\ud800"},
            {"timestamp": at(2), "type": "attachment", "sessionId": "claude-\ud800", "attachment": {
                "type": "hook_success", "hookName": "Stop-\ud800", "hookEvent": "Stop", "stdout": "ok \ud800"}}])
        jl(self.roots["codex"] / "rollout-s.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": "codex-\ud800", "cwd": "/srv/y-\ud800"}},
            {"timestamp": at(1), "type": "event_msg", "payload": {"type": "future-\ud800"}},
            item(at(2), {"type": "UserMessage", "id": "1", "content": text_blocks("still here")})])
        chats = self.roots["gemini"] / "hash" / "chats"
        chats.mkdir(parents=True)
        (chats / "session-s.json").write_text(json.dumps({"sessionId": "gem-\ud800", "startTime": at(0), "lastUpdated": at(1), "messages": [
            {"type": "future-\ud800", "content": "x", "timestamp": at(0)}, {"type": "user", "content": "gem words", "timestamp": at(1)}]}))
        out = self.gather()
        claude = next((out / "sessions").glob("claude-*.md")).read_text(encoding="utf-8")
        self.assertIn("] user: hello \\ud800 there  ", claude)                 # the surrogate is visible as its escape
        self.assertIn("type=future-\\ud800", claude)
        self.assertIn("] hook: Stop-\\ud800 (Stop) succeeded; stdout: ok \\ud800  ", claude)
        self.assertIn("] user: still here  ", next((out / "sessions").glob("codex-*.md")).read_text(encoding="utf-8"))
        self.assertIn("] user: gem words  ", next((out / "sessions").glob("gemini-*.md")).read_text(encoding="utf-8"))
        self.assertTrue((out / "workspace.md").is_file())
        self.assertEqual(len(self.session_ids(out)), 3)

    @unittest.skipUnless(os.name == "posix", "file names are arbitrary bytes only on POSIX")
    def test_a_path_with_bytes_that_are_not_utf8_is_printed_and_written_not_raised(self):
        # A file name can hold any byte; Python reads one it cannot decode as a lone surrogate (here \udcff).
        missing = Path(os.fsdecode(bytes(self.root) + b"/no-such-\xff"))
        out = self.root / "odd-path-run"
        r = run_gather_script(["--since", "2000-01-01", "--out", str(out), "--root", f"codex={self.roots['codex']}",
                               "--root", f"claude={self.roots['claude']}", "--root", f"gemini={missing}"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("gemini: not found, tried ", r.stdout)
        self.assertIn("no-such-\\udcff", r.stdout)
        self.assertIn("no-such-\\udcff", (out / "index.md").read_text(encoding="utf-8"))

    def test_a_line_that_cannot_be_decoded_costs_a_file_that_line_and_no_more(self):
        good1 = json.dumps({"timestamp": at(0), "type": "user", "sessionId": "claude-bad", "message": {"content": "first words"}})
        good2 = json.dumps({"timestamp": at(1), "type": "assistant", "sessionId": "claude-bad",
                            "message": {"content": [{"type": "text", "text": "last words"}]}})
        self.raw_lines(self.roots["claude"] / "proj" / "bad.jsonl", [good1, self.HUGE, self.DEEP, good2])
        codex = [json.dumps({"timestamp": at(0), "type": "session_meta", "payload": {"id": "codex-bad", "cwd": "/srv/a"}}),
                 self.HUGE, self.DEEP, json.dumps(item(at(1), {"type": "UserMessage", "id": "1", "content": text_blocks("codex words")}))]
        self.raw_lines(self.roots["codex"] / "rollout-bad.jsonl", codex)
        chats = self.roots["gemini"] / "hash" / "chats"
        self.raw_lines(chats / "session-bad.jsonl", [
            json.dumps({"sessionId": "gem-bad", "startTime": at(0)}),
            json.dumps({"id": "m1", "type": "user", "content": "gem first", "timestamp": at(1)}), self.HUGE, self.DEEP,
            json.dumps({"id": "m2", "type": "user", "content": "gem last", "timestamp": at(2)})])
        (chats / "session-undecodable.json").write_text(self.DEEP)  # a legacy chat that is one undecodable value
        out = self.gather()
        claude = self.transcript(out, "claude", "claude-bad")
        self.assertIn("] user: first words  ", claude)
        self.assertIn("] agent: last words  ", claude)
        self.assertIn("unparseable line (RecursionError)", claude)
        self.assertIn("] user: codex words  ", self.transcript(out, "codex", "codex-bad"))
        gemini = self.transcript(out, "gemini", "gem-bad")
        self.assertIn("] user: gem first  ", gemini)
        self.assertIn("] user: gem last  ", gemini)
        self.assertIn("unparseable line (RecursionError)", gemini)
        # The chat that is one undecodable value is a session of one note, not a failed run.
        undecodable = next(p for p in (out / "sessions").glob("gemini-*.md") if "gem-bad" not in p.name)
        self.assertIn("unreadable session file (RecursionError", undecodable.read_text(encoding="utf-8"))
        self.assertEqual(len(self.session_ids(out)), 4)


# ---------------------------------------------------------------------------- Claude Code transcripts

class ClaudeTranscriptTest(LogHome):
    """What a healing pass needs from a Claude Code log -- the user's words, hook output, what
    instructions reached the agent -- is in the transcript, and the bookkeeping is not allowed to
    bury it. The records are written by hand in the shapes real Claude Code logs have."""

    INSTRUCTIONS = [str(Path("/srv/agent-fixture/.claude/CLAUDE.md")), str(Path("/srv/agent-fixture/AGENTS.md"))]
    SKILL = str(Path("/srv/agent-fixture/skills/demo-skill/SKILL.md"))
    NESTED = str(Path("/srv/agent-fixture/pkg/CLAUDE.md"))

    def setUp(self):
        super().setUp()
        rows, self.line = [], {}

        def add(kind, **fields):
            rows.append({"timestamp": at(len(rows)), "type": kind, "sessionId": "claude-fixture",
                         "cwd": "/srv/agent-fixture", **fields})
            return len(rows)  # the record's line number in the raw log

        def att(att_type, **fields):
            return add("attachment", attachment={"type": att_type, **fields})

        secret = "ghp_" + "a" * 30  # assembled at run time: nothing secret-shaped is committed
        notice = ("<task-notification>\n<task-id>b1</task-id>\n<output-file>/tmp/fixture/b1.output</output-file>\n"
                  "<status>completed</status>\n<summary>Background command \"cd /srv/x &amp;&amp; make test\" "
                  "completed (exit code 0)</summary>\n<result>RESULT-BODY-NOT-WANTED</result>\n</task-notification>")
        add("user", message={"content": "Please fix the build"})
        add("assistant", message={"content": [{"type": "text", "text": "Running the tests."},
                                               {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "make test"}}]})
        self.line["run_start"] = att("output_style", style="default")
        for _ in range(2):
            att("total_tokens_reminder", text="tokens left")
            att("output_style", style="default")
        att("total_tokens_reminder", text="tokens left")  # six notes in a row, two alternating types
        self.line["run_end"] = len(rows)
        self.line["human"] = att("queued_command", prompt="stop adding mocks, token " + secret,
                                 commandMode="prompt", origin={"kind": "human"}, humanTurn=True)
        self.line["notice"] = att("queued_command", prompt=notice, commandMode="task-notification",
                                  origin={"kind": "task-notification", "producer": "session-task"})
        self.line["notice_bare"] = att("queued_command", commandMode="task-notification", prompt=(
            "<task-notification>\n<status>failed</status>\n<summary>Agent \"audit\" finished</summary>\n</task-notification>"))
        self.line["human_image"] = att("queued_command", commandMode="prompt", origin={"kind": "human"}, humanTurn=True, prompt=[
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "QkFTRTY0LURBVEE" * 20}},
            {"type": "text", "text": "see this screenshot"}])
        self.line["peer"] = att("queued_command", isMeta=True, origin={"kind": "peer", "name": "reviewer"},
                                prompt="<agent-message from=\"a1\">please re-check the diff</agent-message>")
        self.line["coordinator"] = att("queued_command", isMeta=True, origin={"kind": "coordinator"},
                                       prompt="Also report on over-reach")
        self.line["hook_ok"] = att("hook_success", hookName="Stop", hookEvent="Stop", command="node hook.mjs",
                                   content="", stdout="all clear", stderr="", exitCode=0, durationMs=5)
        self.line["hook_error"] = att("hook_non_blocking_error", hookName="PostToolUse:Bash", hookEvent="PostToolUse",
                                      command="lint --all", stdout="", stderr="boom " + secret, exitCode=1)
        self.line["hook_context"] = att("hook_additional_context", hookName="SessionStart", hookEvent="SessionStart",
                                        content=["first context", "second context"])
        self.line["hook_cancelled"] = att("hook_cancelled", hookName="PostToolUse:Bash", hookEvent="PostToolUse",
                                          command="slow-hook", timedOut=True, timeoutMs=30000)
        self.line["hook_message"] = att("hook_system_message", hookName="Stop", hookEvent="Stop", content="Stop blocked")
        self.line["hook_blocked"] = att("hook_blocking_error", hookName="PreToolUse:Bash", hookEvent="PreToolUse",
                                        blockingError={"blockingError": "denied by policy", "command": "guard.sh"})
        self.line["hook_stopped"] = att("hook_stopped_continuation", hookName="PostToolUse:Write", hookEvent="PostToolUse",
                                        message="review required")
        self.line["hook_crashed"] = att("hook_error_during_execution", hookName="PostToolUse:Bash",
                                        hookEvent="PostToolUse", content="hook crashed")
        self.line["hook_permission"] = att("hook_permission_decision", hookEvent="PermissionRequest", decision="allow")
        self.line["instructions"] = att("instructions", reason="compaction", changed=True, files=[
            {"path": self.INSTRUCTIONS[0], "type": "User", "content": "INSTRUCTION-BODY-NOT-WANTED"},
            {"path": self.INSTRUCTIONS[1], "type": "Project", "content": "more body"}])
        self.line["skills"] = att("invoked_skills", skills=[
            {"name": "demo-skill", "path": self.SKILL, "content": "SKILL-BODY-NOT-WANTED"}])
        self.line["listing"] = att("skill_listing", isInitial=True, skillCount=3, names=["alpha", "beta", "gamma"],
                                   content="LISTING-BODY-NOT-WANTED")
        self.line["nested"] = att("nested_memory", path=self.NESTED, displayPath="pkg/CLAUDE.md",
                                  content={"type": "Project", "path": self.NESTED, "content": "NESTED-BODY-NOT-WANTED"})
        self.line["stop_blocked"] = add("system", subtype="stop_hook_summary", level="suggestion", hookCount=2,
                                        hookInfos=[{"command": "a"}, {"command": "b"}], hookErrors=["hook failed"],
                                        hookAdditionalContext=[], preventedContinuation=True, stopReason="tests missing",
                                        hasOutput=True)
        self.line["files_start"] = att("file", filename="a.txt", content={"type": "text", "file": {"filePath": "a.txt"}})
        att("file", filename="b.txt", content={"type": "text", "file": {"filePath": "b.txt"}})
        self.line["files_end"] = att("file", filename="c.txt", content={"type": "text", "file": {"filePath": "c.txt"}})
        add("user", message={"content": "continue"})
        self.line["mixed_start"] = att("future_kind", note="a type this script has never seen")
        att(secret)  # a drifted log can put anything where a type name belongs
        self.line["mixed_end"] = add("system", subtype="stop_hook_summary", level="suggestion", hookCount=1,
                                     hookInfos=[], hookErrors=[], hookAdditionalContext=[], preventedContinuation=False,
                                     stopReason="", hasOutput=False)
        self.rows = rows
        self.raw = self.roots["claude"] / "proj" / "fixture.jsonl"
        jl(self.raw, rows)
        self.out = self.gather()
        self.text = self.transcript(self.out, "claude", "claude-fixture")
        self.lines = self.text.splitlines()
        self.secret = secret

    def at_line(self, key):
        return f"({self.raw}:{self.line[key]})"

    def test_the_users_words_typed_while_the_agent_worked_are_user_messages(self):
        self.assertIn("] user: (sent while the agent was working) stop adding mocks, token [masked]  "
                      + self.at_line("human"), self.text)
        # An image becomes a marker, not its bytes, and the words around it stay.
        self.assertIn("] user: (sent while the agent was working) [image attached] see this screenshot  "
                      + self.at_line("human_image"), self.text)
        self.assertNotIn("QkFTRTY0LURBVEE", self.text)
        # Counted as the user's messages: the first prompt, the two queued ones, and "continue".
        self.assertEqual(self.index_row(self.out, "claude-fixture").split("|")[7].strip(), "4")

    def test_a_task_notification_is_one_short_line_without_its_result(self):
        self.assertIn("] event: task notification (completed): Background command \"cd /srv/x && make test\" "
                      "completed (exit code 0)  " + self.at_line("notice"), self.text)
        self.assertIn("] event: task notification (failed): Agent \"audit\" finished  " + self.at_line("notice_bare"),
                      self.text)
        self.assertNotIn("RESULT-BODY-NOT-WANTED", self.text)
        self.assertNotIn("b1.output", self.text)

    def test_a_message_another_agent_queued_names_its_sender_and_is_not_a_user_message(self):
        self.assertIn("] event: message queued while the agent was working, from peer reviewer: "
                      "<agent-message from=\"a1\">please re-check the diff</agent-message>  " + self.at_line("peer"),
                      self.text)
        self.assertIn("] event: message queued while the agent was working, from coordinator: "
                      "Also report on over-reach  " + self.at_line("coordinator"), self.text)

    def test_hook_output_carries_the_hook_name_event_and_masked_content(self):
        self.assertIn("] hook: Stop succeeded (exit=0); command: node hook.mjs; stdout: all clear  "
                      + self.at_line("hook_ok"), self.text)
        self.assertIn("] hook: PostToolUse:Bash (PostToolUse) failed (non-blocking) (exit=1); command: lint --all; "
                      "stderr: boom [masked]  " + self.at_line("hook_error"), self.text)
        self.assertIn("] hook: SessionStart added context; content: first context second context  "
                      + self.at_line("hook_context"), self.text)
        self.assertIn("] hook: PostToolUse:Bash (PostToolUse) was cancelled (timed out after 30000ms); command: slow-hook  "
                      + self.at_line("hook_cancelled"), self.text)
        self.assertIn("] hook: Stop system message; content: Stop blocked  " + self.at_line("hook_message"), self.text)
        # The other hook outcomes the host writes keep their words in fields of their own.
        self.assertIn('] hook: PreToolUse:Bash (PreToolUse) blocked; blocking error: {"blockingError": '
                      '"denied by policy", "command": "guard.sh"}  ' + self.at_line("hook_blocked"), self.text)
        self.assertIn("] hook: PostToolUse:Write (PostToolUse) stopped the agent; message: review required  "
                      + self.at_line("hook_stopped"), self.text)
        self.assertIn("] hook: PostToolUse:Bash (PostToolUse) errored while running; content: hook crashed  "
                      + self.at_line("hook_crashed"), self.text)
        self.assertIn("] hook: PermissionRequest decided a permission request; decision: allow  "
                      + self.at_line("hook_permission"), self.text)
        self.assertIn("] hook: stop hooks ran (2 hook(s)); prevented the agent from stopping; "
                      "stop reason: tests missing; errors: hook failed  " + self.at_line("stop_blocked"), self.text)
        self.assertNotIn(self.secret, self.text)

    def test_exposure_lines_name_the_files_and_skills_that_reached_the_agent_not_their_text(self):
        self.assertIn(f"] exposure: instructions delivered (compaction, changed): {self.INSTRUCTIONS[0]} [User], "
                      f"{self.INSTRUCTIONS[1]} [Project]  " + self.at_line("instructions"), self.text)
        self.assertIn(f"] exposure: skills invoked: demo-skill ({self.SKILL})  " + self.at_line("skills"), self.text)
        self.assertIn("] exposure: skill listing (initial, 3 skill(s)): alpha, beta, gamma  " + self.at_line("listing"),
                      self.text)
        self.assertIn(f"] exposure: instructions delivered (nested): {self.NESTED} [Project]  " + self.at_line("nested"),
                      self.text)
        for body in ("INSTRUCTION-BODY-NOT-WANTED", "SKILL-BODY-NOT-WANTED", "LISTING-BODY-NOT-WANTED",
                     "NESTED-BODY-NOT-WANTED"):
            self.assertNotIn(body, self.text)

    def test_a_run_of_consecutive_notes_is_one_line_with_counts_and_the_raw_line_range(self):
        first, last = self.line["run_start"], self.line["run_end"]
        self.assertIn(f"[{shown(first - 1)}] note: type=attachment/output_style x3, type=attachment/total_tokens_reminder x3 "
                      f"through {shown(last - 1)}  (raw log lines {first}-{last})", self.lines)
        # Notes of one type only: a count and a range, no type repeated.
        first, last = self.line["files_start"], self.line["files_end"]
        self.assertIn(f"[{shown(first - 1)}] note: type=attachment/file x3 through {shown(last - 1)}  "
                      f"(raw log lines {first}-{last})", self.lines)
        # A type this script has never seen is still named, even beside a bookkeeping record.
        first, last = self.line["mixed_start"], self.line["mixed_end"]
        self.assertIn(f"[{shown(first - 1)}] note: type=attachment/future_kind, type=attachment/[masked], "
                      f"type=system/stop_hook_summary through {shown(last - 1)}  (raw log lines {first}-{last})", self.lines)
        self.assertNotIn(self.secret, self.text)

    def test_the_raw_log_is_named_once_in_the_header_not_on_every_note(self):
        self.assertEqual(self.lines[3], f"raw log: {self.raw}  ")
        notes = [l for l in self.lines if "] note: " in l]
        self.assertTrue(notes)
        for line in notes:
            self.assertNotIn(str(self.raw), line)

    def test_every_raw_line_is_a_rendered_line_or_inside_a_noted_range(self):
        covered = set()
        for line in self.lines[7:]:
            ref = re.search(r"\((?:raw log lines? (\d+)(?:-(\d+))?|" + re.escape(str(self.raw)) + r":(\d+))\)$", line)
            self.assertIsNotNone(ref, line)
            if ref.group(3):
                covered.add(int(ref.group(3)))
            else:
                covered.update(range(int(ref.group(1)), int(ref.group(2) or ref.group(1)) + 1))
        self.assertEqual(covered, set(range(1, len(self.rows) + 1)))

    def test_hook_output_is_bounded_by_max_chars(self):
        jl(self.raw, [{"timestamp": at(0), "type": "attachment", "sessionId": "claude-bound", "attachment": {
            "type": "hook_success", "hookName": "Stop", "hookEvent": "Stop", "stdout": "word " * 2000, "exitCode": 0}}])
        out = self.gather(extra=["--max-chars", "100"])
        line = next(l for l in self.transcript(out, "claude", "claude-bound").splitlines() if "] hook: " in l)
        self.assertIn("[trimmed", line)
        self.assertLess(len(line), 400)


class ClaudeUserRecordTest(LogHome):
    """A user-type record in a Claude Code log is not always the user speaking: its origin says
    who sent it. Background-task notifications and messages from a coordinator or another session
    are events, and only the user's own words are user messages -- the user's corrections are
    what a healing pass reads first."""

    NOTICE = ("<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n"
              "<summary>Background command \"make test\" completed (exit code 0)</summary>\n"
              "<result>RESULT-BODY-NOT-WANTED</result>\n</task-notification>")

    def setUp(self):
        super().setUp()
        rows, self.line = [], {}

        def user(key, content, **fields):
            rows.append({"timestamp": at(len(rows)), "type": "user", "sessionId": "claude-origins",
                         "cwd": "/srv/agent-fixture", "message": {"content": content}, **fields})
            self.line[key] = len(rows)

        failed = "<task-notification>\n<status>failed</status>\n<summary>Agent \"audit\" failed</summary>\n</task-notification>"
        user("prompt", "Please fix the build")                                       # no origin at all
        user("human", "stop adding mocks", origin={"kind": "human"}, turnOrigin="human", promptSource="sdk")
        user("notice", self.NOTICE, origin={"kind": "task-notification", "producer": "session-task"},
             turnOrigin="task_notification", promptSource="system")
        user("notice_blocks", [{"type": "text", "text": self.NOTICE.replace("make test", "make lint")}],
             origin={"kind": "task-notification"})
        user("notice_wrapped", "[SYSTEM NOTIFICATION - NOT USER INPUT]\nThis is an automated background-task event, "
                               "NOT a message from the user.\n\n" + failed, isMeta=True, origin={"kind": "task-notification"})
        user("coordinator", "The coordinator sent a message while you were working:\nAlso report on over-reach",
             isMeta=True, origin={"kind": "coordinator"})
        user("peer", "Another Claude session sent a message:\nplease re-check", isMeta=True,
             origin={"kind": "peer", "name": "reviewer", "from": "a1"})
        # A compaction summary carries the same turnOrigin a notification does, and no origin.
        user("summary", "This session is being continued from a previous conversation that ran out of context.",
             isCompactSummary=True, turnOrigin="task_notification")
        user("no_kind", "typed words", origin={})
        self.raw = self.roots["claude"] / "proj" / "origins.jsonl"
        jl(self.raw, rows)
        self.out = self.gather()
        self.text = self.transcript(self.out, "claude", "claude-origins")

    def at_line(self, key):
        return f"({self.raw}:{self.line[key]})"

    def test_task_notifications_are_event_lines_in_every_shape_they_come_in(self):
        self.assertIn("] event: task notification (completed): Background command \"make test\" completed "
                      "(exit code 0)  " + self.at_line("notice"), self.text)
        self.assertIn("] event: task notification (completed): Background command \"make lint\" completed "
                      "(exit code 0)  " + self.at_line("notice_blocks"), self.text)
        self.assertIn("] event: task notification (failed): Agent \"audit\" failed  " + self.at_line("notice_wrapped"),
                      self.text)
        self.assertNotIn("RESULT-BODY-NOT-WANTED", self.text)
        self.assertNotIn("] user: <task-notification", self.text)
        self.assertNotIn("] user: [SYSTEM NOTIFICATION", self.text)

    def test_messages_from_a_coordinator_or_another_session_name_their_sender(self):
        self.assertIn("] event: message from coordinator: The coordinator sent a message while you were working: "
                      "Also report on over-reach  " + self.at_line("coordinator"), self.text)
        self.assertIn("] event: message from peer reviewer: Another Claude session sent a message: please re-check  "
                      + self.at_line("peer"), self.text)

    def test_only_the_users_own_words_are_user_messages(self):
        users = [l.split("] user: ", 1)[1].rsplit("  (", 1)[0] for l in self.text.splitlines() if "] user: " in l]
        self.assertEqual(users[:2], ["Please fix the build", "stop adding mocks"])
        self.assertIn("typed words", users)  # an origin without a kind says nothing about who sent it
        self.assertEqual(self.index_row(self.out, "claude-origins").split("|")[7].strip(), str(len(users)))
        self.assertEqual(len(users), 3)  # the three above: not the compaction summary either
        self.assertEqual(self.text.count("] event: "), 5)

    def test_text_blocks_are_one_message_each_run_and_keep_their_order_around_a_tool_result(self):
        jl(self.roots["claude"] / "proj" / "blocks.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "claude-blocks", "message": {"content": [
                {"type": "text", "text": "first words"}, {"type": "text", "text": "more first words"},
                {"type": "tool_result", "tool_use_id": "t1", "content": "the result"},
                {"type": "text", "text": "words after the result"}]}}])
        lines = [l.split("] ", 1)[1].split("  (")[0] for l in self.transcript(self.gather(), "claude", "claude-blocks").splitlines()
                 if l.startswith("[")]
        self.assertEqual(lines, ["user: first words more first words", "tool_result: tool result (id=t1, error=False): the result",
                                 "user: words after the result"])

    def test_a_compaction_summary_is_not_mistaken_for_a_notification_by_its_turn_origin(self):
        line = next(l for l in self.text.splitlines() if "This session is being continued" in l)
        self.assertIn("] summary (agent-written): This session is being continued", line)
        self.assertNotIn("task notification", line)


class ClaudeThinkingTest(LogHome):
    """The reasoning a Claude Code log keeps in the clear is the agent's own account at the time,
    so a thinking block with text is a line of its own -- labeled as reasoning, not an agent
    message, bounded, and masked. A block that keeps only its signature stays a note."""

    LONG = " ".join(f"w{n:04d}" for n in range(400))  # 2,400 characters; word n ends at character 6n + 5

    def setUp(self):
        super().setUp()
        rows, self.line = [], {}

        def add(key, role, blocks):
            rows.append({"timestamp": at(len(rows)), "type": role, "sessionId": "claude-reasoning",
                         "cwd": "/srv/agent-fixture", "message": {"content": blocks}})
            self.line[key] = len(rows)

        self.secret = "ghp_" + "a" * 30  # assembled at run time: nothing secret-shaped is committed
        add("prompt", "user", "Why does the build fail?")
        add("short", "assistant", [{"type": "thinking", "thinking": "The failure is in the\nlinker step.", "signature": "c2ln"}])
        add("empty", "assistant", [{"type": "thinking", "thinking": "", "signature": "c2ln"}])
        add("mixed", "assistant", [{"type": "thinking", "thinking": "Check the log first.", "signature": "c2ln"},
                                   {"type": "text", "text": "Looking at the log."},
                                   {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "make"}}])
        add("long", "assistant", [{"type": "thinking", "thinking": self.LONG, "signature": "c2ln"}])
        add("secret", "assistant", [{"type": "thinking", "thinking": "The token " + self.secret + " is in the env.",
                                     "signature": "c2ln"}])
        add("boundary", "assistant", [{"type": "thinking", "thinking": "a" * 1500 + "b" * 500, "signature": "c2ln"}])
        self.raw = self.roots["claude"] / "proj" / "reasoning.jsonl"
        jl(self.raw, rows)
        self.out = self.gather()
        self.text = self.transcript(self.out, "claude", "claude-reasoning")

    def at_line(self, key):
        return f"({self.raw}:{self.line[key]})"

    def test_a_thinking_block_with_text_is_a_thinking_line_not_an_agent_message(self):
        self.assertIn("] thinking: The failure is in the linker step.  " + self.at_line("short"), self.text)
        row = self.index_row(self.out, "claude-reasoning").split("|")
        self.assertEqual(row[7].strip(), "1")  # user messages: only the prompt
        self.assertEqual(row[8].strip(), "1")  # agent messages: only the text block, not four reasoning blocks

    def test_reasoning_keeps_its_place_among_the_blocks_of_a_turn(self):
        lines = [l for l in self.text.splitlines() if self.at_line("mixed") in l]
        self.assertEqual([l.split("] ", 1)[1].split(":", 1)[0] for l in lines], ["thinking", "agent", "tool_call"])
        self.assertIn("] thinking: Check the log first.  ", lines[0])

    def test_a_thinking_block_that_keeps_only_its_signature_is_still_a_note(self):
        n = self.line["empty"]
        self.assertIn(f"] note: assistant content block type=thinking  (raw log line {n})", self.text)
        self.assertEqual(self.text.count("] thinking: "), 5)  # the other five blocks have text

    def test_reasoning_is_cut_at_1500_characters_with_a_marker(self):
        line = next(l for l in self.text.splitlines() if self.at_line("long") in l)
        # The first 1,500 characters end with word 249; the marker says where the rest is.
        self.assertIn("w0249... [trimmed; full text at " + f"{self.raw}:{self.line['long']}]", line)
        self.assertNotIn("w0250", line)

    def test_reasoning_is_cut_after_exactly_1500_characters(self):
        # Words would hide a cut one character early or late: here every character is the same up to the cut.
        line = next(l for l in self.text.splitlines() if self.at_line("boundary") in l)
        self.assertIn("] thinking: " + "a" * 1500 + "... [trimmed; full text at ", line)
        self.assertNotIn("a" * 1501, line)
        self.assertNotIn("bbbbb", line)

    def test_reasoning_is_cut_at_max_chars_when_that_is_smaller(self):
        out = self.gather(extra=["--max-chars", "100"])
        line = next(l for l in self.transcript(out, "claude", "claude-reasoning").splitlines() if self.at_line("long") in l)
        self.assertIn("] thinking: w0000 w0001", line)
        self.assertIn("w0015 w001... [trimmed; full text at ", line)  # characters 96-99 are the start of word 16

    def test_reasoning_is_masked_like_everything_else(self):
        self.assertIn("] thinking: The token [masked] is in the env.  " + self.at_line("secret"), self.text)
        self.assertNotIn(self.secret, self.text)


class CompactionSummaryTest(LogHome):
    """A compaction summary is text the agent wrote to carry its context forward; the logs store
    it as a user-role message. Shown as the user it would read as the user's own account of the
    work, so it is a labeled summary line, bounded and masked like other long text, and never one
    of the user's messages."""

    LONG = " ".join(f"w{n:04d}" for n in range(500))  # 3,000 characters; word n starts at character 6n

    def setUp(self):
        super().setUp()
        rows, self.line = [], {}

        def add(key, role, content, session="claude-compaction", **fields):
            rows.append({"timestamp": at(len(rows)), "type": role, "sessionId": session, "cwd": "/srv/agent-fixture",
                         **({"message": {"content": content}} if role == "user" else {}), **fields})
            self.line[key] = len(rows)

        self.secret = "ghp_" + "a" * 30  # assembled at run time: nothing secret-shaped is committed
        add("prompt", "user", "Please fix the build")
        add("boundary", "system", None, subtype="compact_boundary")
        add("summary", "user", "This session is being continued from a previous conversation. Its token was "
            + self.secret + ".", isCompactSummary=True, isVisibleInTranscriptOnly=True)
        add("blocks", "user", [{"type": "text", "text": "Summary, first block."}, {"type": "text", "text": "Summary, second block."}],
            isCompactSummary=True)
        add("long", "user", self.LONG, isCompactSummary=True)
        add("after", "user", "continue")
        self.raw = self.roots["claude"] / "proj" / "compaction.jsonl"
        jl(self.raw, rows)

        chats = self.roots["gemini"] / "hash" / "chats"
        chats.mkdir(parents=True)
        self.gem_raw = chats / "session-compression.json"
        self.gem_raw.write_text(json.dumps({"sessionId": "gem-compression", "startTime": at(0), "lastUpdated": at(5), "messages": [
            {"type": "user", "content": "Fix the build", "timestamp": at(0)},
            {"type": "gemini", "content": "On it.", "timestamp": at(1)},
            {"type": "user", "content": [{"text": "<state_snapshot>\n<overall_goal>fix the build</overall_goal>\n</state_snapshot>"}],
             "timestamp": at(2)},
            {"type": "gemini", "content": "Got it. Thanks for the additional context!", "timestamp": at(3)},
            {"type": "user", "content": "thanks, and note the <state_snapshot> tag in my own words", "timestamp": at(4)}]}))
        self.out = self.gather()
        self.text = self.transcript(self.out, "claude", "claude-compaction")
        self.gem = self.transcript(self.out, "gemini", "gem-compression")

    def at_line(self, key):
        return f"({self.raw}:{self.line[key]})"

    def test_a_summary_stored_as_a_user_message_is_a_labeled_agent_written_line(self):
        self.assertIn("] summary (agent-written): This session is being continued from a previous conversation. "
                      "Its token was [masked].  " + self.at_line("summary"), self.text)
        self.assertNotIn(self.secret, self.text)
        self.assertNotIn("] user: This session is being continued", self.text)

    def test_a_summary_stored_as_blocks_is_one_line_with_all_its_text(self):
        lines = [l for l in self.text.splitlines() if self.at_line("blocks") in l]
        self.assertEqual([l.split("] ", 1)[1].split("  (")[0] for l in lines],
                         ["summary (agent-written): Summary, first block. Summary, second block."])

    def test_a_long_summary_is_cut_at_the_usual_bound_with_the_usual_marker(self):
        line = next(l for l in self.text.splitlines() if self.at_line("long") in l)
        # The first 2,000 characters end partway into word 333.
        self.assertIn("] summary (agent-written): w0000 w0001", line)
        self.assertIn("w0332 w0... [trimmed; full text at " + f"{self.raw}:{self.line['long']}]", line)
        self.assertNotIn("w0333", line)

    def test_the_summary_is_not_one_of_the_users_messages(self):
        users = [l for l in self.text.splitlines() if "] user: " in l]
        self.assertEqual(len(users), 2)  # the first prompt and "continue"
        self.assertIn("] user: continue  " + self.at_line("after"), self.text)
        self.assertEqual(self.index_row(self.out, "claude-compaction").split("|")[7].strip(), "2")
        self.assertIn("] compaction: compaction (session summarized)  " + self.at_line("boundary"), self.text)

    def test_a_codex_compaction_record_carries_its_summary_as_a_labeled_agent_written_line(self):
        # Codex keeps the summary in the compaction record's message, and the user messages it retains
        # in its replacement history (which are already lines of the transcript, from when they were sent).
        wrapped = {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "Another language model started to solve this problem. Summary: Short summary."}]}
        rows = [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": "codex-compaction", "cwd": "/srv/agent-fixture"}},
            item(at(1), {"type": "UserMessage", "id": "1", "content": text_blocks("Please fix the build")}),
            {"timestamp": at(2), "type": "compacted", "payload": {
                "message": "Short summary, with a token " + self.secret + ".", "replacement_history": [wrapped]}},
            {"timestamp": at(3), "type": "compacted", "payload": {"message": self.LONG}},
            {"timestamp": at(4), "type": "compacted", "payload": {"message": "   "}},
            {"timestamp": at(5), "type": "compacted", "payload": {}},
            item(at(6), {"type": "UserMessage", "id": "2", "content": text_blocks("continue")})]
        raw = self.roots["codex"] / "rollout-compaction.jsonl"
        jl(raw, rows)
        text = self.transcript(self.gather(), "codex", "codex-compaction")
        lines = text.splitlines()
        # The compaction line, then its summary, for the same record.
        i = lines.index(f"[{shown(2)}] compaction: compaction (session summarized)  ({raw}:3)")
        self.assertEqual(lines[i + 1], f"[{shown(2)}] summary (agent-written): Short summary, with a token [masked].  ({raw}:3)")
        self.assertNotIn(self.secret, text)
        # A long one is cut at the usual bound with the usual marker.
        long_line = next(l for l in lines if f"({raw}:4)" in l and "summary (agent-written)" in l)
        self.assertIn("w0332 w0... [trimmed; full text at " + f"{raw}:4]", long_line)
        self.assertNotIn("w0333", long_line)
        # A blank or absent message has no summary to show; all four are still compactions.
        self.assertEqual(text.count("] summary (agent-written): "), 2)
        self.assertEqual(text.count("] compaction: "), 4)
        # The summary is not the user's, and the wrapped copy in the replacement history is not a line of its own.
        self.assertEqual([l.split("] user: ", 1)[1].split("  (")[0] for l in lines if "] user: " in l],
                         ["Please fix the build", "continue"])
        self.assertNotIn("Another language model", text)

    def test_a_gemini_chat_s_summary_is_labeled_as_one_whose_author_the_log_does_not_record(self):
        # The CLI writes its compression summary itself and stores it as a user message. Nothing in the log
        # says a person wrote this one, so it is not the user's: provenance protects a record proven to be
        # a person's, not an unknown one. The text is kept; it is not counted as a user message.
        label = "summary (agent-written, as far as the log shows)"
        self.assertIn(f"] {label}: <state_snapshot> <overall_goal>fix the build</overall_goal> </state_snapshot>  "
                      f"({self.gem_raw}#msg2)", self.gem)
        users = [l.split("] user: ", 1)[1].split("  (")[0] for l in self.gem.splitlines() if "] user: " in l]
        self.assertEqual(users, ["Fix the build", "thanks, and note the <state_snapshot> tag in my own words"])
        self.assertEqual(self.index_row(self.out, "gem-compression").split("|")[7].strip(), "2")


class GeminiSnapshotTest(LogHome):
    """The CLI's own compression summary, a user-role message that begins with <state_snapshot>, in
    each shape of Gemini chat log and in a chat the CLI drives itself."""

    LABEL = "summary (agent-written, as far as the log shows)"

    def snapshot(self, body="<overall_goal>fix the build</overall_goal>"):
        return f"<state_snapshot>\n{body}\n</state_snapshot>"

    def test_in_an_append_only_chat_and_in_a_chat_the_cli_drives_it_is_the_same_summary(self):
        chats = self.roots["gemini"] / "hash" / "chats"
        (chats / "gem-parent").mkdir(parents=True)
        rows = [{"sessionId": "gem-jsonl", "startTime": at(0)},
                {"id": "m1", "type": "user", "content": "Fix the build", "timestamp": at(1)},
                {"id": "m2", "type": "user", "content": [{"text": self.snapshot()}], "timestamp": at(2)},
                {"id": "m3", "type": "user", "content": "go on", "timestamp": at(3)}]
        jl(chats / "session-main.jsonl", rows)
        jl(chats / "gem-parent" / "gem-sub.jsonl", [{"sessionId": "gem-sub", "startTime": at(0)},
                                                    {"id": "s1", "type": "user", "content": "Get Started!", "timestamp": at(1)},
                                                    {"id": "s2", "type": "user", "content": self.snapshot(), "timestamp": at(2)}])
        out = self.gather()
        main = self.transcript(out, "gemini", "gem-jsonl")
        self.assertIn(f"] {self.LABEL}: <state_snapshot> <overall_goal>fix the build</overall_goal> </state_snapshot>  ", main)
        self.assertEqual([l.split("] user: ", 1)[1].split("  (")[0] for l in main.splitlines() if "] user: " in l],
                         ["Fix the build", "go on"])
        self.assertEqual(self.index_row(out, "gem-jsonl").split("|")[7].strip(), "2")
        # In a chat the CLI drives, the summary is still the summary, and the other message is still the harness's.
        sub = self.transcript(out, "gemini", "gem-sub")
        self.assertIn(f"] {self.LABEL}: <state_snapshot> ", sub)
        self.assertIn("] message (from the harness): Get Started!  ", sub)
        self.assertEqual(self.index_row(out, "gem-sub").split("|")[7].strip(), "0")

    def test_the_text_is_kept_masked_and_bounded_like_any_summary(self):
        token = "ghp_" + "a" * 30
        chats = self.roots["gemini"] / "hash" / "chats"
        chats.mkdir(parents=True)
        (chats / "session-long.json").write_text(json.dumps({"sessionId": "gem-long", "startTime": at(0), "lastUpdated": at(1), "messages": [
            {"type": "user", "content": "\n  " + self.snapshot(f"<key_knowledge>the token is {token}</key_knowledge>" + " word" * 400),
             "timestamp": at(0)}]}))
        out = self.gather(extra=["--max-chars", "300"])
        lines = [l for l in self.transcript(out, "gemini", "gem-long").splitlines() if f"] {self.LABEL}: " in l]
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn("the token is [masked]", line)
        self.assertNotIn(token, line)
        self.assertIn("... [trimmed; full text at ", line)

    def test_a_message_that_only_mentions_the_tag_is_the_users(self):
        chats = self.roots["gemini"] / "hash" / "chats"
        chats.mkdir(parents=True)
        (chats / "session-mention.json").write_text(json.dumps({"sessionId": "gem-mention", "startTime": at(0), "lastUpdated": at(1), "messages": [
            {"type": "user", "content": "what is a <state_snapshot> for?", "timestamp": at(0)}]}))
        text = self.transcript(self.gather(), "gemini", "gem-mention")
        self.assertIn("] user: what is a <state_snapshot> for?  ", text)
        self.assertNotIn(self.LABEL, text)


class DelegationBriefTest(LogHome):
    """A subagent or side thread starts with a brief the delegating agent wrote. It is agent-written
    text in a user-role record, so it is a labeled line and not one of the user's messages. A thread
    a person started keeps its first message as the user's."""

    BRIEF = "Review the diff and report defects"

    def user(self, rows, key, content, **fields):
        rows.append({"timestamp": at(len(rows)), "type": "user", "sessionId": "claude-parent", "isSidechain": True,
                     "agentId": "aaa", "cwd": "/srv/agent-fixture", "message": {"content": content}, **fields})
        self.line[key] = len(rows)

    def setUp(self):
        super().setUp()
        self.line = {}
        rows = []
        # The record before the brief: a notice, a person, and something the harness inserted. None of
        # them is the delegating agent's writing, so none is the brief and none uses up its place.
        notice = "<task-notification>\n<status>completed</status>\n<summary>Background command done</summary>\n</task-notification>"
        self.user(rows, "notice", notice, origin={"kind": "task-notification"})
        self.user(rows, "person", "typed by a person", origin={"kind": "human"})
        self.user(rows, "meta", "[Image: source: /srv/agent-fixture/shot.png]", isMeta=True)
        self.user(rows, "brief", [{"type": "text", "text": self.BRIEF}, {"type": "text", "text": "Report in one page."}])
        rows.append({"timestamp": at(len(rows)), "type": "assistant", "sessionId": "claude-parent", "isSidechain": True,
                     "agentId": "aaa", "message": {"content": [{"type": "text", "text": "Reviewing."}]}})
        self.user(rows, "later", "A second message from the delegating side")
        self.raw = self.roots["claude"] / "proj" / "main" / "subagents" / "agent-aaa.jsonl"
        jl(self.raw, rows)
        jl(self.roots["claude"] / "proj" / "main.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "claude-parent", "cwd": "/srv/agent-fixture",
             "message": {"content": "Please review my change"}}])
        # A delegated Codex thread whose first user-role record is a UserMessage item, and a top-level one.
        jl(self.roots["codex"] / "rollout-delegate.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": "codex-delegate", "cwd": "/srv/agent-fixture",
                                                                       "source": {"subagent": {"thread_spawn": {"parent_thread_id": "p"}}}}},
            item(at(1), {"type": "UserMessage", "id": "1", "content": text_blocks("Check the logs and report")}),
            item(at(2), {"type": "AgentMessage", "id": "2", "content": text_blocks("Checking.")})])
        jl(self.roots["codex"] / "rollout-top.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": "codex-top", "cwd": "/srv/agent-fixture", "source": "exec"}},
            item(at(1), {"type": "UserMessage", "id": "1", "content": text_blocks("Fix the build")})])
        self.out = self.gather()

    def sub_text(self):
        return next(p for p in (self.out / "sessions").glob("claude-claude-parent-*.md")).read_text(encoding="utf-8")

    def at_line(self, key):
        return f"({self.raw}:{self.line[key]})"

    def test_the_first_user_role_record_a_delegating_agent_wrote_is_its_brief(self):
        text = self.sub_text()
        # Both text blocks of that one record are the brief: one message, one line.
        self.assertIn("] brief (from the delegating agent): " + self.BRIEF + " Report in one page.  " + self.at_line("brief"), text)
        self.assertEqual(text.count("] brief (from the delegating agent): "), 1)
        self.assertNotIn("] user: " + self.BRIEF, text)

    def test_what_comes_before_the_brief_is_not_taken_for_it(self):
        text = self.sub_text()
        self.assertIn("] event: task notification (completed): Background command done  " + self.at_line("notice"), text)
        self.assertIn("] user: typed by a person  " + self.at_line("person"), text)
        self.assertIn("] message (from the harness): [Image: source: /srv/agent-fixture/shot.png]  " + self.at_line("meta"), text)

    def test_only_the_first_record_is_the_brief_and_a_later_one_is_a_message_from_the_delegating_side(self):
        text = self.sub_text()
        self.assertEqual(text.count("] brief (from the delegating agent): "), 1)  # the one record, however many blocks
        self.assertIn("] message (from the delegating side): A second message from the delegating side  "
                      + self.at_line("later"), text)

    def test_the_brief_is_not_counted_as_a_user_message(self):
        text = self.sub_text()
        row = next(l for l in (self.out / "index.md").read_text(encoding="utf-8").splitlines()
                   if l.startswith("| claude ") and "yes" in l.split("|")[10])
        self.assertEqual(row.split("|")[7].strip(), str(text.count("] user: ")))
        # Only the person: neither the brief, nor the harness insert, nor the later message is a user message.
        self.assertEqual(text.count("] user: "), 1)

    def test_a_thread_a_person_started_keeps_its_first_message_as_the_users(self):
        main = self.transcript(self.out, "claude", "claude-parent")
        self.assertIn("] user: Please review my change  ", main)
        self.assertNotIn("brief (from", main)
        top = self.transcript(self.out, "codex", "codex-top")
        self.assertIn("] user: Fix the build  ", top)
        self.assertEqual(self.index_row(self.out, "codex-top").split("|")[7].strip(), "1")

    def test_in_a_transcript_that_mixes_threads_only_the_delegated_records_are_briefs(self):
        # Not every Claude Code log keeps a subagent in a file of its own: some flag the records.
        jl(self.roots["claude"] / "mixed" / "mixed.jsonl", [
            {"timestamp": at(0), "type": "assistant", "sessionId": "claude-mixed", "isSidechain": True,
             "message": {"content": [{"type": "text", "text": "Starting the delegated work."}]}},
            {"timestamp": at(1), "type": "user", "sessionId": "claude-mixed", "message": {"content": "main prompt"}},
            {"timestamp": at(2), "type": "user", "sessionId": "claude-mixed", "isSidechain": True,
             "message": {"content": "delegated task"}},
            {"timestamp": at(3), "type": "user", "sessionId": "claude-mixed", "message": {"content": "another main prompt"}}])
        text = self.transcript(self.gather(), "claude", "claude-mixed")
        self.assertIn("] user: main prompt  ", text)
        self.assertIn("] brief (from the delegating agent): delegated task  ", text)
        self.assertIn("] user: another main prompt  ", text)

    def test_a_delegated_codex_threads_first_user_role_item_is_its_brief(self):
        sub = self.transcript(self.out, "codex", "codex-delegate")
        self.assertIn("] brief (from the delegating agent): Check the logs and report  ", sub)
        self.assertNotIn("] user: ", sub)
        self.assertEqual(self.index_row(self.out, "codex-delegate").split("|")[7].strip(), "0")


class ProvenanceTest(LogHome):
    """Provenance outranks content. A record a person wrote is the user's message however its text
    begins -- a person may paste a system reminder, an AGENTS.md, or a state snapshot for review -- and
    where it begins with a block the harness may have added, its line says so and keeps all of the
    text. Nothing is moved out of the user's message and nothing is left uncounted. Only where nothing
    says a person wrote a record does its content label it."""

    LINKED = "Linked sessions now (status, not an instruction)\nsession-a idle"
    FLAG = "[begins with a block the harness may have added] "

    def setUp(self):
        super().setUp()
        rows, self.line = [], {}

        def user(key, content, **fields):
            rows.append({"timestamp": at(len(rows)), "type": "user", "sessionId": "claude-provenance",
                         "cwd": "/srv/agent-fixture", "message": {"content": content}, **fields})
            self.line[key] = len(rows)

        def queued(key, prompt):
            rows.append({"timestamp": at(len(rows)), "type": "attachment", "sessionId": "claude-provenance", "attachment": {
                "type": "queued_command", "prompt": prompt, "commandMode": "prompt", "origin": {"kind": "human"},
                "humanTurn": True}})
            self.line[key] = len(rows)

        def block(text, attributes=""):
            return f"<system-reminder{attributes}>\n{text}\n</system-reminder>"

        self.secret = "ghp_" + "a" * 30  # assembled at run time: nothing secret-shaped is committed
        self.block = block
        human = {"origin": {"kind": "human"}}
        user("human", [{"type": "text", "text": block(self.LINKED)}, {"type": "text", "text": "ignore the older versions"}], **human)
        user("pasted", block("pasted for review"), **human)
        user("agents_md", "# AGENTS.md instructions for /srv/agent-fixture\n\nbe brief", **human)
        user("snapshot", "<state_snapshot>\n<overall_goal>fix the build</overall_goal>\n</state_snapshot>", **human)
        user("two_in_one", [{"type": "text", "text": block("first note") + "\n" + block("second note", ' id="x1"')},
                            {"type": "text", "text": "words after two"}], **human)
        user("string", block("started without a mode") + "\n" + block("second") + "\nPlease fix the build")
        user("mid", "Look at <system-reminder>quoted by me</system-reminder> in my notes")
        user("unclosed", "<system-reminder>never closed, then my words")
        user("long", [{"type": "text", "text": block("r" * 1000)}, {"type": "text", "text": "after the long one"}], **human)
        user("secret", block("token " + self.secret + " in the context") + "\nwords after the secret")
        user("meta_blocks", [{"type": "text", "text": block("meta context")}, {"type": "text", "text": "meta words"}], isMeta=True)
        queued("queued", block("Linked sessions now") + "\n\nignore the older versions")
        queued("queued_only", block("only context"))
        self.raw = self.roots["claude"] / "proj" / "provenance.jsonl"
        jl(self.raw, rows)
        # A delegated thread whose brief begins with a block, and a person's thread that does too.
        jl(self.roots["claude"] / "proj" / "main" / "subagents" / "agent-aaa.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "claude-provenance-parent", "isSidechain": True, "agentId": "aaa",
             "message": {"content": block("harness note") + "\nReview the diff"}}])
        # Codex: a person's turn (a UserMessage item, with its twin) that begins like an AGENTS.md; and a response-stream
        # message that begins the same way and that no item accounts for.
        pasted = "# AGENTS.md instructions for /srv/agent-fixture\n\nplease review this file"
        jl(self.roots["codex"] / "rollout-provenance.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {"id": "codex-provenance", "cwd": "/srv/agent-fixture"}},
            {"timestamp": at(1), "type": "response_item", "payload": {"type": "message", "role": "user",
                                                                      "content": [{"type": "input_text", "text": pasted}]}},
            item(at(1), {"type": "UserMessage", "id": "1", "content": text_blocks(pasted)}),
            {"timestamp": at(2), "type": "response_item", "payload": {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "# AGENTS.md instructions for /srv/agent-fixture\n\nnothing but the harness"}]}}])
        # Gemini: nothing in its log says who wrote a user message, and the CLI writes its own summary as one.
        chats = self.roots["gemini"] / "hash" / "chats"
        chats.mkdir(parents=True)
        (chats / "session-a.json").write_text(json.dumps({"sessionId": "gem-provenance", "startTime": at(0), "lastUpdated": at(2), "messages": [
            {"type": "user", "content": "<state_snapshot>\n<overall_goal>fix it</overall_goal>\n</state_snapshot>", "timestamp": at(0)},
            {"type": "gemini", "content": "Got it. Thanks for the additional context!", "timestamp": at(1)},
            {"type": "user", "content": "thanks", "timestamp": at(2)}]}))
        self.out = self.gather()
        self.text = self.transcript(self.out, "claude", "claude-provenance")

    def at_line(self, key):
        return f"({self.raw}:{self.line[key]})"

    def shown(self, *blocks):
        return " ".join(" ".join(b.split()) for b in blocks)

    def test_a_person_s_record_that_begins_with_a_harness_block_is_one_flagged_user_message_with_all_its_text(self):
        self.assertIn("] user: " + self.FLAG + self.shown(self.block(self.LINKED), "ignore the older versions") + "  "
                      + self.at_line("human"), self.text)
        record = [l for l in self.text.splitlines() if self.at_line("human") in l]
        self.assertEqual(len(record), 1)  # one message: not an event line and a message, not a line for each block
        self.assertNotIn("] event: ", self.text)

    def test_blocks_only_in_a_person_s_record_are_still_the_users_message(self):
        self.assertIn("] user: " + self.FLAG + self.shown(self.block("pasted for review")) + "  " + self.at_line("pasted"), self.text)
        self.assertIn("] user: " + self.FLAG + self.shown(self.block("first note"), self.block("second note", ' id="x1"'))
                      + " words after two  " + self.at_line("two_in_one"), self.text)

    def test_text_that_begins_like_other_harness_blocks_is_the_users_when_a_person_wrote_it(self):
        self.assertIn("] user: # AGENTS.md instructions for /srv/agent-fixture be brief  " + self.at_line("agents_md"), self.text)
        self.assertIn("] user: <state_snapshot> <overall_goal>fix the build</overall_goal> </state_snapshot>  "
                      + self.at_line("snapshot"), self.text)

    def test_a_record_with_no_sign_of_who_wrote_it_is_flagged_not_demoted(self):
        self.assertIn("] user: " + self.FLAG + self.shown(self.block("started without a mode"), self.block("second"))
                      + " Please fix the build  " + self.at_line("string"), self.text)
        self.assertIn("] user: " + self.FLAG + "<system-reminder>never closed, then my words  " + self.at_line("unclosed"), self.text)

    def test_the_tag_in_the_middle_of_the_words_is_not_a_flag(self):
        self.assertIn("] user: Look at <system-reminder>quoted by me</system-reminder> in my notes  " + self.at_line("mid"), self.text)

    def test_a_long_block_is_cut_short_so_the_words_after_it_survive_the_bound(self):
        lead = "<system-reminder> " + "r" * (200 - len("<system-reminder> "))
        self.assertIn("] user: " + self.FLAG + lead + "... [trimmed; full text at " + f"{self.raw}:{self.line['long']}] after the long one  "
                      + self.at_line("long"), self.text)
        self.assertNotIn("r" * 201, self.text)

    def test_what_is_shown_is_masked_and_a_flag_on_the_record_still_marks_the_text(self):
        self.assertIn("] user: " + self.FLAG + "<system-reminder> token [masked] in the context </system-reminder> words after the secret  "
                      + self.at_line("secret"), self.text)
        self.assertNotIn(self.secret, self.text)
        self.assertIn("] user: " + self.FLAG + self.shown(self.block("meta context")) + " meta words (meta)  " + self.at_line("meta_blocks"),
                      self.text)

    def test_a_message_typed_while_the_agent_worked_is_flagged_the_same_way(self):
        self.assertIn("] user: (sent while the agent was working) " + self.FLAG + self.shown(self.block("Linked sessions now"))
                      + " ignore the older versions  " + self.at_line("queued"), self.text)
        self.assertIn("] user: (sent while the agent was working) " + self.FLAG + self.shown(self.block("only context")) + "  "
                      + self.at_line("queued_only"), self.text)
        self.assertNotIn("type=attachment/queued_command", self.text)

    def test_every_one_of_them_is_counted_as_a_user_message(self):
        users = [l for l in self.text.splitlines() if "] user: " in l]
        self.assertEqual(len(users), 13)  # one per record: none moved out, none dropped
        self.assertEqual(self.index_row(self.out, "claude-provenance").split("|")[7].strip(), "13")

    def test_a_delegating_agents_brief_that_begins_with_a_block_is_flagged_too(self):
        sub = next(p for p in (self.out / "sessions").glob("claude-claude-provenance-parent*.md")).read_text(encoding="utf-8")
        self.assertIn("] brief (from the delegating agent): " + self.FLAG + self.shown(self.block("harness note")) + " Review the diff  ", sub)

    def test_a_codex_user_turn_that_begins_like_an_agents_md_is_the_users_and_flagged(self):
        text = self.transcript(self.out, "codex", "codex-provenance")
        users = [l for l in text.splitlines() if "] user: " in l]
        self.assertEqual(len(users), 1)  # the item; its twin is not a second line
        self.assertIn("] user: " + self.FLAG + "# AGENTS.md instructions for /srv/agent-fixture please review this file  ", users[0])
        self.assertEqual(self.index_row(self.out, "codex-provenance").split("|")[7].strip(), "1")

    def test_a_codex_response_stream_message_nothing_accounts_for_is_labeled_by_its_content(self):
        text = self.transcript(self.out, "codex", "codex-provenance")
        self.assertNotIn("nothing but the harness", text)
        self.assertIn("response_item/message: 2 record(s) not individually rendered", text)  # the twin, and this one

    def test_a_gemini_message_that_begins_with_a_snapshot_is_a_summary_of_unrecorded_author_not_the_users(self):
        text = self.transcript(self.out, "gemini", "gem-provenance")
        self.assertIn("] summary (agent-written, as far as the log shows): "
                      "<state_snapshot> <overall_goal>fix it</overall_goal> </state_snapshot>  ", text)
        self.assertIn("] user: thanks  ", text)
        self.assertNotIn("] user: <state_snapshot>", text)
        self.assertNotIn(self.FLAG + "<state_snapshot>", text)
        self.assertEqual(self.index_row(self.out, "gem-provenance").split("|")[7].strip(), "1")


class DelegatedThreadTest(LogHome):
    """No person speaks in a thread another agent started. After its brief, what arrives in user-role
    records is the delegating side's or the harness's, and says so: a message from the delegating
    side, or one the harness inserted. A person's own record (origin human) is still the user's, and
    the same text in a thread a person started is still the user's."""

    def setUp(self):
        super().setUp()
        self.line = {}
        rows = []

        def user(key, content, **fields):
            rows.append({"timestamp": at(len(rows)), "type": "user", "sessionId": "claude-delegate", "isSidechain": True,
                         "agentId": "aaa", "cwd": "/srv/agent-fixture", "message": {"content": content}, **fields})
            self.line[key] = len(rows)

        user("brief", "Review the diff and report defects")
        user("workflow", "[Workflow harness — computed the inputs for this step]\n{\"files\": 3}")
        user("interrupted", "[Request interrupted by user]")
        user("image", "[Image: source: /srv/agent-fixture/shot.png]", isMeta=True)
        user("command", [{"type": "text", "text": "<command-message>demo-skill</command-message>"},
                         {"type": "text", "text": "Base directory for this skill: /srv/agent-fixture/skills/demo"}], isMeta=True)
        user("plain_meta", "A note the harness inserted", isMeta=True)
        user("person", "typed by a person", origin={"kind": "human"})
        self.raw = self.roots["claude"] / "proj" / "main" / "subagents" / "agent-aaa.jsonl"
        jl(self.raw, rows)
        # The same texts in a thread a person started.
        jl(self.roots["claude"] / "proj" / "main.jsonl", [
            {"timestamp": at(0), "type": "user", "sessionId": "claude-delegate", "message": {"content": "Please review my change"}},
            {"timestamp": at(1), "type": "user", "sessionId": "claude-delegate", "message": {"content": "[Request interrupted by user]"}},
            {"timestamp": at(2), "type": "user", "sessionId": "claude-delegate", "isMeta": True,
             "message": {"content": "[Image: source: /srv/agent-fixture/shot.png]"}}])
        # Codex: a guardian-style side thread that is asked again and again, and a spawned thread told twice.
        guard = [{"timestamp": at(0), "type": "session_meta", "payload": {
            "id": "codex-guardian", "cwd": "/srv/agent-fixture", "source": {"subagent": {"other": "guardian"}}}}]
        for n in range(3):
            guard.append({"timestamp": at(n + 1), "type": "response_item", "payload": {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": f"The following is the Codex agent history to assess, part {n + 1}"}]}})
        jl(self.roots["codex"] / "rollout-guardian.jsonl", guard)
        jl(self.roots["codex"] / "rollout-spawned.jsonl", [
            {"timestamp": at(0), "type": "session_meta", "payload": {
                "id": "codex-spawned", "cwd": "/srv/agent-fixture", "source": {"subagent": {"thread_spawn": {"parent_thread_id": "p"}}}}},
            item(at(1), {"type": "UserMessage", "id": "1", "content": text_blocks("Check the logs and report")}),
            item(at(2), {"type": "UserMessage", "id": "2", "content": text_blocks("Also check the config")})])
        # Gemini: a chat a subagent ran, driven by the CLI, beside the user's own chat.
        chats = self.roots["gemini"] / "hash" / "chats"
        (chats / "gem-parent").mkdir(parents=True)
        (chats / "session-main.json").write_text(json.dumps({"sessionId": "gem-parent", "startTime": at(0), "lastUpdated": at(1), "messages": [
            {"type": "user", "content": "Please investigate the build", "timestamp": at(0)}]}))
        (chats / "gem-parent" / "session-sub.json").write_text(json.dumps({"sessionId": "gem-sub", "startTime": at(0), "lastUpdated": at(2), "messages": [
            {"type": "user", "content": "Get Started!", "timestamp": at(0)},
            {"type": "gemini", "content": "Looking.", "timestamp": at(1)},
            {"type": "user", "content": "You have run out of turns. Call complete_task now.", "timestamp": at(2)}]}))
        self.out = self.gather()

    def sub_text(self):
        return next(p for p in (self.out / "sessions").glob("claude-claude-delegate-*.md")).read_text(encoding="utf-8")

    def at_line(self, key):
        return f"({self.raw}:{self.line[key]})"

    def test_what_the_delegating_side_sends_after_the_brief_is_labeled_as_theirs(self):
        text = self.sub_text()
        self.assertIn("] brief (from the delegating agent): Review the diff and report defects  " + self.at_line("brief"), text)
        self.assertIn("] message (from the delegating side): [Workflow harness — computed the inputs for this step] "
                      "{\"files\": 3}  " + self.at_line("workflow"), text)
        self.assertIn("] message (from the delegating side): [Request interrupted by user]  " + self.at_line("interrupted"), text)

    def test_what_the_harness_inserts_is_labeled_as_the_harness_s(self):
        text = self.sub_text()
        self.assertIn("] message (from the harness): [Image: source: /srv/agent-fixture/shot.png]  " + self.at_line("image"), text)
        # Both text blocks of the record are one line, with no "(meta)" tag left over: the label says whose it is.
        self.assertIn("] message (from the harness): <command-message>demo-skill</command-message> "
                      "Base directory for this skill: /srv/agent-fixture/skills/demo  " + self.at_line("command"), text)
        self.assertIn("] message (from the harness): A note the harness inserted  " + self.at_line("plain_meta"), text)
        self.assertNotIn("(meta)", text)

    def test_only_a_person_s_own_record_in_a_delegated_thread_is_a_user_message(self):
        text = self.sub_text()
        users = [l for l in text.splitlines() if "] user: " in l]
        self.assertEqual(len(users), 1)
        self.assertIn("] user: typed by a person  " + self.at_line("person"), text)
        row = next(l for l in (self.out / "index.md").read_text(encoding="utf-8").splitlines()
                   if l.startswith("| claude ") and "yes" in l.split("|")[10])
        self.assertEqual(row.split("|")[7].strip(), "1")

    def test_the_same_texts_in_a_thread_a_person_started_are_still_the_users(self):
        main = self.transcript(self.out, "claude", "claude-delegate")
        for line in ("] user: Please review my change  ", "] user: [Request interrupted by user]  ",
                     "] user: [Image: source: /srv/agent-fixture/shot.png]  "):
            self.assertIn(line, main)
        self.assertNotIn("message (from", main)

    def test_a_codex_side_thread_that_is_asked_again_and_again_is_the_delegating_sides(self):
        text = self.transcript(self.out, "codex", "codex-guardian")
        self.assertIn("] brief (from the delegating agent): The following is the Codex agent history to assess, part 1 "
                      "(response_item message)  ", text)
        for n in (2, 3):
            self.assertIn(f"] message (from the delegating side): The following is the Codex agent history to assess, part {n} "
                          "(response_item message)  ", text)
        self.assertNotIn("] user: ", text)
        self.assertEqual(self.index_row(self.out, "codex-guardian").split("|")[7].strip(), "0")

    def test_a_codex_spawned_thread_told_twice_has_a_brief_and_a_message(self):
        text = self.transcript(self.out, "codex", "codex-spawned")
        self.assertIn("] brief (from the delegating agent): Check the logs and report  ", text)
        self.assertIn("] message (from the delegating side): Also check the config  ", text)
        self.assertEqual(self.index_row(self.out, "codex-spawned").split("|")[7].strip(), "0")

    def test_a_gemini_subagent_chat_is_driven_by_the_cli_and_the_users_own_chat_is_not(self):
        sub = self.transcript(self.out, "gemini", "gem-sub")
        self.assertIn("] message (from the harness): Get Started!  ", sub)
        self.assertIn("] message (from the harness): You have run out of turns. Call complete_task now.  ", sub)
        self.assertIn("] agent: Looking.  ", sub)
        self.assertNotIn("] user: ", sub)
        self.assertEqual(self.index_row(self.out, "gem-sub").split("|")[7].strip(), "0")
        main = self.transcript(self.out, "gemini", "gem-parent")
        self.assertIn("] user: Please investigate the build  ", main)


# ---------------------------------------------------------------------------- Codex transcripts

class CodexTranscriptTest(LogHome):
    """Codex records that carry the user's or the agent's words, tool calls, or hook output are
    lines of their own, whichever record they arrive in; what a rendered record already says is
    not said twice."""

    def setUp(self):
        super().setUp()
        rows, self.line = [], {}

        def add(record, key=None):
            record = {"timestamp": at(len(rows)), **record}
            rows.append(record)
            if key:
                self.line[key] = len(rows)

        def done(key, it):
            add({"type": "event_msg", "payload": {"type": "item_completed", "item": it}}, key)

        def message(key, role, text):
            block = "output_text" if role == "assistant" else "input_text"
            add({"type": "response_item", "payload": {"type": "message", "role": role,
                                                       "content": [{"type": block, "text": text}]}}, key)

        add({"type": "session_meta", "payload": {"id": "codex-fixture", "cwd": "/srv/agent-fixture", "source": "exec"}})
        done("user", {"type": "UserMessage", "id": "u1", "content": text_blocks("Please fix the build")})
        message("user_twin", "user", "Please fix the build")                      # repeats the item above
        message("agents_md", "user", "# AGENTS.md instructions for /srv/agent-fixture\n\nbody")  # injected context
        message("hook_message", "user", '<hook_prompt hook_run_id="stop:1:/srv/fx/hooks.json">Before you finish</hook_prompt>')
        done("hook", {"type": "HookPrompt", "id": "h1", "fragments": [
            {"text": "Before you finish, re-check", "hookRunId": "stop:1:/srv/fx/hooks.json"}]})
        done("collab", {"type": "CollabAgentToolCall", "id": "c1", "tool": "wait", "status": "completed",
                        "sender_thread_id": "t1", "receiver_thread_ids": ["t2"], "receiver_agents": [], "agents_states": {}})
        done("subagent", {"type": "SubAgentActivity", "id": "c2", "kind": "started", "agent_thread_id": "t2",
                          "agent_path": "/root/worker", "model": "fixture-model", "reasoning_effort": "high"})
        done("result", {"type": "FunctionCallOutput", "id": "f1", "name": "send_message_to_thread",
                        "namespace": "codex_app", "output": "delivered"})
        message("answer_only", "assistant", "Only the response stream has this answer")
        done("answer", {"type": "AgentMessage", "id": "a1", "content": text_blocks("Twin answer")})
        message("answer_twin", "assistant", "Twin answer")                       # repeats the item above
        message("developer", "developer", "<permissions>read-only</permissions>")
        message("delegated", "user", "Delegated follow-up: check the logs")
        add({"type": "event_msg", "payload": {"type": "turn_aborted", "reason": "interrupted"}}, "aborted")
        add({"type": "response_item", "payload": {"type": "image_generation_call", "id": "ig1", "status": "completed",
                                                   "revised_prompt": "a red circle", "result": "A" * 100}}, "image")
        add({"type": "event_msg", "payload": {"type": "token_count", "info": {}}}, "telemetry")
        self.raw = self.roots["codex"] / "rollout-fixture.jsonl"
        jl(self.raw, rows)
        # A delegated agent's rollout: its task exists only as a response_item message.
        sub = []
        sub.append({"timestamp": at(0), "type": "session_meta", "payload": {
            "id": "codex-delegate", "cwd": "/srv/agent-fixture", "source": {"subagent": {"thread_spawn": {"parent_thread_id": "t1"}}}}})
        sub.append({"timestamp": at(1), "type": "response_item", "payload": {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "# AGENTS.md instructions for /srv/agent-fixture\n\nbody"}]}})
        sub.append({"timestamp": at(2), "type": "response_item", "payload": {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "Review the diff and report defects"}]}})
        self.sub_raw = self.roots["codex"] / "rollout-delegate.jsonl"
        jl(self.sub_raw, sub)
        self.out = self.gather()
        self.text = self.transcript(self.out, "codex", "codex-fixture")
        self.lines = self.text.splitlines()

    def at_line(self, key):
        return f"({self.raw}:{self.line[key]})"

    def test_user_words_are_lines_and_nothing_is_said_twice_or_made_up(self):
        user_lines = [l for l in self.lines if "] user: " in l]
        self.assertEqual(len(user_lines), 2, user_lines)  # not the repeated message, not injected context
        self.assertIn("] user: Please fix the build  " + self.at_line("user"), self.text)
        self.assertIn("] user: Delegated follow-up: check the logs (response_item message)  " + self.at_line("delegated"),
                      self.text)
        self.assertNotIn("AGENTS.md instructions for", "\n".join(user_lines))

    def test_a_delegated_agents_task_is_a_line_even_when_only_the_response_stream_has_it(self):
        sub = self.transcript(self.out, "codex", "codex-delegate")
        self.assertIn("] brief (from the delegating agent): Review the diff and report defects (response_item message)  "
                      + f"({self.sub_raw}:3)", sub)
        self.assertNotIn("] user: ", sub)

    def test_agent_answers_that_only_the_response_stream_has_are_lines_and_twins_are_not_repeated(self):
        agent_lines = [l for l in self.lines if "] agent: " in l]
        self.assertEqual(len(agent_lines), 2, agent_lines)
        self.assertIn("] agent: Only the response stream has this answer (response_item message)  "
                      + self.at_line("answer_only"), self.text)
        self.assertIn("] agent: Twin answer  " + self.at_line("answer"), self.text)

    def test_hook_prompts_subagent_tools_and_host_tool_results_are_lines_of_their_own(self):
        self.assertIn("] hook: hook prompt stop:1:/srv/fx/hooks.json: Before you finish, re-check  "
                      + self.at_line("hook"), self.text)
        collab = next(l for l in self.lines if "] tool_call: collab wait status=completed" in l)
        self.assertIn('"receiver_thread_ids": ["t2"]', collab)
        self.assertTrue(collab.endswith(self.at_line("collab")))
        self.assertIn("] tool_call: subagent started: /root/worker (thread t2, model fixture-model, effort high)  "
                      + self.at_line("subagent"), self.text)
        self.assertIn("] tool_result: call result (codex_app.send_message_to_thread): delivered  "
                      + self.at_line("result"), self.text)
        self.assertNotIn("item_completed/HookPrompt", self.text)
        self.assertNotIn("item_completed/CollabAgentToolCall", self.text)
        self.assertNotIn("item_completed/SubAgentActivity", self.text)
        self.assertNotIn("item_completed/FunctionCallOutput", self.text)

    def test_a_generated_image_is_named_by_its_size_not_dumped(self):
        self.assertIn('] tool_call: image_generation_call: {"status": "completed", "revised_prompt": "a red circle", '
                      '"result": "(100 chars of image data)"}  ' + self.at_line("image"), self.text)
        self.assertNotIn("A" * 20, self.text)

    def test_what_stays_a_note_is_counted_and_located(self):
        n = self.line["aborted"]
        self.assertIn(f"[{shown(n - 1)}] note: type=turn_aborted  (raw log line {n})", self.lines)
        # The five response_item messages that repeat a rendered line, are injected context, or are
        # the developer's instructions: counted, with the range they cover.
        self.assertIn("[] note: response_item/message: 5 record(s) not individually rendered "
                      "(redundant with item_completed unless noted otherwise)  "
                      f"(raw log lines {self.line['user_twin']}-{self.line['developer']})", self.lines)


class CodexOccurrenceTest(LogHome):
    """Codex writes most messages twice: to its response stream, and as a completed item. A
    response-stream record is a repeat only of an item of its own. A second "continue" an hour
    later is a second "continue" -- repeating the same words is evidence the skill relies on -- and
    two typed seconds apart are two."""

    def setUp(self):
        super().setUp()
        rows = []

        def when(seconds):
            return (CLOCK + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        def stream(seconds, role, text):  # the response-stream record
            block = "output_text" if role == "assistant" else "input_text"
            rows.append({"timestamp": when(seconds), "type": "response_item", "payload": {
                "type": "message", "role": role, "content": [{"type": block, "text": text}]}})

        def done(seconds, kind, text):  # the completed item
            rows.append(item(when(seconds), {"type": kind, "id": str(len(rows)), "content": text_blocks(text)}))

        rows.append({"timestamp": when(0), "type": "session_meta", "payload": {"id": "codex-occurrences", "cwd": "/srv/agent-fixture"}})
        stream(600.0, "user", "continue")      # 2: the response stream first, as real rollouts write a user turn...
        done(600.3, "UserMessage", "continue")  # 3: ...then its item: a pair
        stream(4200.0, "user", "continue")     # 4: an hour on, the response stream alone: a second "continue"
        done(7800.0, "UserMessage", "continue")  # 5: another hour on, an item alone: a third
        stream(9000.0, "user", "keep going")   # 6, 7: a pair...
        done(9000.1, "UserMessage", "keep going")
        stream(9005.0, "user", "keep going")   # 8, 9: ...and another, five seconds later
        done(9005.1, "UserMessage", "keep going")
        stream(9100.0, "user", "ok then")      # 10, 11: a pair...
        done(9100.1, "UserMessage", "ok then")
        stream(9102.0, "user", "ok then")      # 12: ...and two seconds later one more with no item of its own: an item twins one record
        done(10000.0, "AgentMessage", "Done.")  # 13: an agent's answer: the item first, as real rollouts write one...
        stream(10000.6, "assistant", "Done.")   # 14: ...then its response-stream record: a pair
        stream(13600.0, "assistant", "Done.")   # 15: an hour later, the response stream alone: a second answer
        self.raw = self.roots["codex"] / "rollout-occurrences.jsonl"
        jl(self.raw, rows)
        self.out = self.gather()
        self.text = self.transcript(self.out, "codex", "codex-occurrences")

    def lines(self, kind):
        return [l.split(f"] {kind}: ", 1)[1] for l in self.text.splitlines() if f"] {kind}: " in l]

    def test_a_second_continue_is_not_taken_for_a_repeat_of_the_first(self):
        raw = self.raw
        self.assertEqual(self.lines("user"), [
            f"continue  ({raw}:3)",                                    # the pair of lines 2 and 3, once
            f"continue (response_item message)  ({raw}:4)",           # an hour later, with no item: its own
            f"continue  ({raw}:5)",                                    # another hour later, an item alone
            f"keep going  ({raw}:7)", f"keep going  ({raw}:9)",       # two pairs, five seconds apart: two
            f"ok then  ({raw}:11)", f"ok then (response_item message)  ({raw}:12)",  # one item, two records: the extra one counts
        ])

    def test_an_agent_answer_repeated_later_is_a_second_answer(self):
        raw = self.raw
        self.assertEqual(self.lines("agent"), [f"Done.  ({raw}:13)", f"Done. (response_item message)  ({raw}:15)"])

    def test_each_occurrence_is_counted_once(self):
        row = self.index_row(self.out, "codex-occurrences").split("|")
        self.assertEqual((row[7].strip(), row[8].strip()), ("7", "2"))  # user and agent messages
        self.assertIn("response_item/message: 5 record(s) not individually rendered", self.text)  # the five that were repeats


class CodexUntimestampedTwinTest(LogHome):
    """Where a response-stream record or its item has no timestamp, nothing says how far apart they were
    written, so only a neighbour can be a twin: the completed item next to it in the file, with no other
    record of the same words between. Anything else is its own occurrence, and is rendered."""

    def setUp(self):
        super().setUp()
        rows = []

        def when(seconds):
            return (CLOCK + dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

        def stream(seconds, role, text):  # the response-stream record; no timestamp when `seconds` is None
            block = "output_text" if role == "assistant" else "input_text"
            row = {"type": "response_item", "payload": {"type": "message", "role": role, "content": [{"type": block, "text": text}]}}
            rows.append(row if seconds is None else {"timestamp": when(seconds), **row})

        def done(seconds, kind, text):  # the completed item
            row = {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": kind, "id": str(len(rows)), "content": text_blocks(text)}}}
            rows.append(row if seconds is None else {"timestamp": when(seconds), **row})

        rows.append({"timestamp": when(0), "type": "session_meta", "payload": {"id": "codex-untimed", "cwd": "/srv/agent-fixture"}})
        stream(None, "user", "continue")      # 2: no timestamp...
        stream(3600, "user", "continue")      # 3: ...then the same words an hour on, with their item next:
        done(3601, "UserMessage", "continue")  # 4: lines 3 and 4 are a pair, and line 2 is a "continue" of its own
        stream(None, "user", "go on")         # 5, 6: neither has a timestamp, and they are neighbours: a pair
        done(None, "UserMessage", "go on")
        stream(3700, "user", "ok")            # 7, 8: the item has none: neighbours still
        done(None, "UserMessage", "ok")
        stream(None, "user", "yes")           # 9, 10: the record has none: neighbours still
        done(3800, "UserMessage", "yes")
        stream(None, "user", "again")         # 11, 12, 13: two records of the same words, one item: the item is
        stream(None, "user", "again")         # next to the second one only, so the first is a "again" of its own
        done(None, "UserMessage", "again")
        done(None, "AgentMessage", "Done.")   # 14, 15: an agent's answer, the item first as real rollouts write it
        stream(None, "assistant", "Done.")
        stream(None, "user", "thanks")        # 16, 17, 18: other words between a record and its item do not part them
        stream(None, "user", "something else")
        done(None, "UserMessage", "thanks")
        stream(None, "user", "sure")          # 19, 20, 21: an item beside two records takes one of them, not both
        done(None, "UserMessage", "sure")
        stream(None, "user", "sure")
        self.raw = self.roots["codex"] / "rollout-untimed.jsonl"
        jl(self.raw, rows)
        self.out = self.gather()
        self.text = self.transcript(self.out, "codex", "codex-untimed")

    def lines(self, kind):
        return [l.split(f"] {kind}: ", 1)[1] for l in self.text.splitlines() if f"] {kind}: " in l]

    def test_a_record_with_no_timestamp_does_not_take_another_occurrences_item(self):
        raw = self.raw
        self.assertEqual(self.lines("user"), [
            f"continue (response_item message)  ({raw}:2)",   # no neighbour item: its own occurrence
            f"continue  ({raw}:4)",                           # the pair of lines 3 and 4, once
            f"go on  ({raw}:6)",
            f"ok  ({raw}:8)",
            f"yes  ({raw}:10)",
            f"again (response_item message)  ({raw}:11)",     # the first of two: the item is the second's neighbour
            f"again  ({raw}:13)",
            f"something else (response_item message)  ({raw}:17)",
            f"thanks  ({raw}:18)",
            f"sure  ({raw}:20)",
            f"sure (response_item message)  ({raw}:21)",
        ])

    def test_an_agent_answer_is_paired_with_the_item_before_it(self):
        self.assertEqual(self.lines("agent"), [f"Done.  ({self.raw}:14)"])

    def test_each_occurrence_is_counted_once(self):
        row = self.index_row(self.out, "codex-untimed").split("|")
        self.assertEqual((row[7].strip(), row[8].strip()), ("11", "1"))  # user and agent messages


# ---------------------------------------------------------------------------- Gemini transcripts

class GeminiTranscriptTest(LogHome):
    def test_a_note_gives_its_message_number_not_the_path(self):
        chats = self.roots["gemini"] / "hash" / "chats"
        chats.mkdir(parents=True)
        raw = chats / "session-notes.json"
        raw.write_text(json.dumps({"sessionId": "gem-notes", "startTime": at(0), "lastUpdated": at(4), "messages": [
            {"type": "user", "content": "hello", "timestamp": at(0)},
            {"type": "gemini", "content": "hi", "timestamp": at(1)},
            {"type": "info", "content": "a notice the CLI showed", "timestamp": at(2)},
            {"type": "info", "content": "another notice", "timestamp": at(3)},
            {"type": "user", "content": "thanks", "timestamp": at(4)}]}))
        text = self.transcript(self.gather(), "gemini", "gem-notes")
        self.assertIn(f"[{shown(2)}] note: type=info x2 through {shown(3)}  (raw log messages 2-3)", text.splitlines())
        self.assertNotIn(str(raw), "\n".join(l for l in text.splitlines() if "] note: " in l))

    def test_a_run_of_notes_found_by_raw_line_and_by_message_number_keeps_both_ranges(self):
        # In a chat log of one record per line, a line that is not a record is located by its raw line and
        # a message the CLI showed (info) by its number among the messages; here they form one run of notes.
        chats = self.roots["gemini"] / "hash" / "chats"
        chats.mkdir(parents=True)
        (chats / "session-mixed.jsonl").write_text("\n".join([
            json.dumps({"sessionId": "gem-mixed", "startTime": at(0)}),                                  # line 1
            "this line is not a record",                                                                  # line 2
            json.dumps({"id": "m1", "type": "info", "content": "a notice", "timestamp": at(1)}),         # line 3, message 0
            "neither is this one",                                                                        # line 4
            json.dumps({"id": "m2", "type": "info", "content": "another notice", "timestamp": at(2)}),   # line 5, message 1
            json.dumps({"id": "m3", "type": "user", "content": "thanks", "timestamp": at(3)})]) + "\n")  # line 6, message 2
        text = self.transcript(self.gather(), "gemini", "gem-mixed")
        self.assertIn(f"[{shown(1)}] note: unparseable line x2, type=info x2 through {shown(2)}  "
                      "(raw log lines 2-4, messages 0-1)", text.splitlines())


# ---------------------------------------------------------------------------- notes, in isolation

class NoteRunTest(unittest.TestCase):
    """How notes become lines, on every shape of run, without any log files."""

    def session(self):
        return gather.Session("claude", Path("raw.jsonl"))

    def lines(self, s):
        return [line for _, line in gather.session_lines(s)]

    def test_a_single_note_has_no_count_and_no_end_time(self):
        s = self.session()
        s.note("2026-01-01T00:00:01Z", "type=a", ("line", 5))
        self.assertEqual(self.lines(s), ["[2026-01-01T00:00:01+00:00] note: type=a  (raw log line 5)"])

    def test_consecutive_notes_of_one_type_are_one_line_with_a_count_and_their_range(self):
        s = self.session()
        for ts, n in (("2026-01-01T00:00:01Z", 5), ("2026-01-01T00:00:02Z", 6), ("2026-01-01T00:00:09Z", 9)):
            s.note(ts, "type=a", ("line", n))
        self.assertEqual(self.lines(s), [
            "[2026-01-01T00:00:01+00:00] note: type=a x3 through 2026-01-01T00:00:09+00:00  (raw log lines 5-9)"])

    def test_interleaved_types_keep_first_appearance_order_and_per_type_counts(self):
        s = self.session()
        for label, n in (("type=a", 1), ("type=b", 2), ("type=a", 3), ("type=c", 4), ("type=b", 5)):
            s.note("2026-01-01T00:00:00Z", label, ("line", n))
        self.assertEqual(self.lines(s), [
            "[2026-01-01T00:00:00+00:00] note: type=a x2, type=b x2, type=c  (raw log lines 1-5)"])

    def test_a_rendered_entry_ends_the_run(self):
        s = self.session()
        s.note("2026-01-01T00:00:01Z", "type=a", ("line", 1))
        s.add("2026-01-01T00:00:02Z", "user", "hello", "raw.jsonl:2")
        s.note("2026-01-01T00:00:03Z", "type=a", ("line", 3))
        self.assertEqual(self.lines(s), [
            "[2026-01-01T00:00:01+00:00] note: type=a  (raw log line 1)",
            "[2026-01-01T00:00:02+00:00] user: hello  (raw.jsonl:2)",
            "[2026-01-01T00:00:03+00:00] note: type=a  (raw log line 3)"])

    def test_an_aggregate_note_is_never_merged_with_its_neighbors(self):
        s = self.session()
        s.note("2026-01-01T00:00:01Z", "type=a", ("line", 1))
        s.note(None, "response_item/x: 4 record(s) not individually rendered", ("line", 2, 9), solo=True)
        s.note("2026-01-01T00:00:03Z", "type=a", ("line", 10))
        self.assertEqual(self.lines(s), [
            "[2026-01-01T00:00:01+00:00] note: type=a  (raw log line 1)",
            "[] note: response_item/x: 4 record(s) not individually rendered  (raw log lines 2-9)",
            "[2026-01-01T00:00:03+00:00] note: type=a  (raw log line 10)"])

    def test_notes_without_timestamps_use_the_first_stamp_there_is(self):
        s = self.session()
        s.note(None, "type=a", ("line", 1))
        s.note(None, "type=b", ("line", 2))
        s.note("2026-01-01T00:00:05Z", "type=a", ("line", 3))
        self.assertEqual(self.lines(s), [
            "[2026-01-01T00:00:05+00:00] note: type=a x2, type=b  (raw log lines 1-3)"])
        t = self.session()
        t.note(None, "unparseable line", ("line", 7))
        self.assertEqual(self.lines(t), ["[] note: unparseable line  (raw log line 7)"])

    def test_messages_and_the_whole_file_are_located_by_their_own_words(self):
        s = self.session()
        s.note(None, "type=info", ("msg", 1))
        s.note(None, "type=info", ("msg", 3))
        s.add(None, "agent", "ok", "raw.json#msg4")
        s.note(None, "unreadable session file", None)
        self.assertEqual(self.lines(s), [
            "[] note: type=info x2  (raw log messages 1-3)",
            "[] agent: ok  (raw.json#msg4)",
            "[] note: unreadable session file  (raw log)"])

    def test_a_run_of_raw_lines_and_message_numbers_keeps_the_range_of_each_in_the_order_they_appear(self):
        s = self.session()
        s.note(None, "unparseable line", ("line", 2))
        s.note(None, "type=info", ("msg", 0))
        s.note(None, "unparseable line", ("line", 9))
        s.note(None, "type=info", ("msg", 3))
        t = self.session()
        t.note(None, "type=info", ("msg", 4))
        t.note(None, "unparseable line", ("line", 7))
        self.assertEqual(self.lines(s), ["[] note: unparseable line x2, type=info x2  (raw log lines 2-9, messages 0-3)"])
        self.assertEqual(self.lines(t), ["[] note: type=info, unparseable line  (raw log message 4, line 7)"])

    def test_a_whole_file_note_in_a_run_keeps_its_place_beside_the_ranges(self):
        s = self.session()
        s.note(None, "unrecognized messages shape", None)
        s.note(None, "type=info", ("msg", 1))
        s.note(None, "type=info", ("msg", 2))
        self.assertEqual(self.lines(s), [
            "[] note: unrecognized messages shape, type=info x2  (raw log messages 1-2, whole file)"])

    def test_a_label_built_from_log_content_is_masked_and_bounded(self):
        s = self.session()
        s.note(None, "type=" + "ghp_" + "a" * 30 + "x" * 500, ("line", 1))
        text = self.lines(s)[0]
        self.assertNotIn("ghp_", text)
        self.assertLess(len(text), 400)


class TaskNoticeTest(unittest.TestCase):
    def test_the_first_words_stand_in_when_a_notice_has_no_summary(self):
        line = gather.claude_task_notice("<task-notification>\n<status>killed</status>\nsomething stopped\n"
                                         "</task-notification>", 2000, "raw:1")
        self.assertEqual(line, "task notification (killed): <task-notification> <status>killed</status> "
                               "something stopped </task-notification>")

    def test_a_notice_with_nothing_recognizable_is_still_a_line(self):
        self.assertEqual(gather.claude_task_notice("plain words", 2000, "raw:1"), "task notification: plain words")


# ---------------------------------------------------------------------------- the suite's own git

class GitIsolationTest(unittest.TestCase):
    """The git these tests run ignores the developer's global configuration, whatever it says."""

    def test_a_global_setting_that_would_break_every_commit_does_not_reach_the_suites_git(self):
        import unittest.mock as mock
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        hostile = tmp / "gitconfig"
        hostile.write_text(f"[commit]\n\tgpgsign = true\n[gpg]\n\tprogram = {(tmp / 'no-such-signer').as_posix()}\n")
        repo = tmp / "repo"
        repo.mkdir()
        identity = ["-c", "user.name=a", "-c", "user.email=a@b"]
        with mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(hostile)}):
            git(repo, "init", "-q", "-b", "main")
            (repo / "f").write_text("x")
            git(repo, "add", "f")
            # The control: the same commit, with that configuration in force, cannot be made.
            bitten = subprocess.run(["git", "-C", str(repo), *identity, "commit", "-qm", "init"],
                                    capture_output=True, text=True, env=dict(os.environ))
            self.assertNotEqual(bitten.returncode, 0, "the hostile configuration should have broken this commit")
            git(repo, *identity, "commit", "-qm", "init")


class MaskingTest(unittest.TestCase):
    """mask() must not turn ordinary words into false positives, and must not leave real
    secret-shaped strings or evidence-destroying hex runs on the wrong side of the line."""

    def test_does_not_mask_ordinary_hyphenated_words(self):
        self.assertEqual(gather.mask("Add a task-management-system module"), "Add a task-management-system module")
        self.assertEqual(gather.mask("ask-for-confirmation-first"), "ask-for-confirmation-first")
        self.assertEqual(gather.mask("Use bearer authentication"), "Use bearer authentication")

    def test_leaves_a_bare_git_sha_or_sha256_digest_unmasked(self):
        sha1 = "a1b2c3d4" * 5  # 40 hex chars
        sha256 = "a1b2c3d4" * 8  # 64 hex chars
        self.assertIn(sha1, gather.mask(f"commit {sha1}"))
        self.assertIn(sha256, gather.mask(f"digest {sha256}"))

    def test_masks_real_secret_shapes(self):
        cases = [
            "Authorization: Bearer sk-ant-abc123def456",
            "ghp_" + "a1b2c3" * 5,
            "glpat-" + "aB3cD4eF5gH6iJ7kL8m9",
            "AIza" + "SyDaB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uX",
            "Authorization: Basic QWxhZGRpbjpvcGVuc2VzYW1lMTIz",
            'password: "hunter22"',
        ]
        for text in cases:
            self.assertIn("[masked]", gather.mask(text), text)

    def test_masks_json_shaped_credentials_in_every_way_they_are_written(self):
        # The closing quote sits between the key and the colon, and may itself be escaped (JSON inside a
        # JSON string, as a tool call's arguments are); the key may continue a longer, joined name.
        for text in ('{"password": "hunter22"}', '{"password":"hunter22"}', '{\\"password\\": \\"hunter22\\"}',
                     "{'password': 'hunter22'}", '{"client_secret": "abcdef123456"}', '{"access_token":"abcdef123456"}',
                     '{"api_key": "abcdef123456"}', '{"x-api-key": "abcdef123456"}', 'DB_PASSWORD=hunter22',
                     'export GITHUB_TOKEN=abcdef123456', '{"password": 12345678}'):
            out = gather.mask(text)
            self.assertNotIn("hunter22", out, text)
            self.assertNotIn("abcdef123456", out, text)
            self.assertNotIn("12345678", out, text)
            self.assertIn("[masked]", out, text)

    def test_masks_the_whole_of_a_quoted_credential_even_with_spaces_in_it(self):
        # A quoted value runs to the quote that closes it, however many words that makes; the text
        # around it stays. (Expected by hand: the key and its quotes up to the value's last character
        # become one marker, the closing quote and what follows stay.)
        cases = {
            '{"password": "short passphrase"}': '{"[masked]"}',
            '{"password": "correct horse battery staple"}': '{"[masked]"}',
            "{'password': 'correct horse battery staple'}": "{'[masked]'}",
            "password = 'correct horse battery staple' # kept": "[masked]' # kept",
            '{"password": "it\'s a secret phrase", "user": "bob"}': '{"[masked]", "user": "bob"}',
            '{"password": "say \\"hello there\\" now"}': '{"[masked]"}',
            '{\\"password\\": \\"short passphrase\\"}': '{\\"[masked]\\"}',
            '{"api_key": "two words here", "n": 1}': '{"[masked]", "n": 1}',
            'TOKEN: "one two three"': '[masked]"',
            # No closing quote on the line: the value is taken to run to the end of it, and no further.
            '{"password": "correct horse battery staple': '{"[masked]',
            'token: "abc def ghi\nnext line stays': '[masked]\nnext line stays',
        }
        for text, expected in cases.items():
            self.assertEqual(gather.mask(text), expected, text)
            self.assertEqual(gather.mask_known(text), expected, text)

    def test_a_quoted_credential_is_masked_whole_however_deep_the_json_around_it_is(self):
        # JSON inside a JSON string, inside another, and so on, as a tool call's arguments hold a command
        # that holds a request body: each level escapes every quote (and backslash) of the one inside it.
        def escaped(text, levels):
            for _ in range(levels):
                text = json.dumps(text)[1:-1]
            return text
        for levels in range(6):
            text = escaped('{"password": "short passphrase", "user": "bob"}', levels)
            expected = escaped('{"', levels) + "[masked]" + escaped('", "user": "bob"}', levels)
            self.assertEqual(gather.mask(text), expected, levels)
            self.assertEqual(gather.mask_known(text), expected, levels)

    def test_a_quoted_value_too_short_to_be_a_credential_is_left_alone(self):
        for text in ('{"password": "a b"}', "{'secret': 'x y'}", 'token: ""', '{"token": "ab cd"}'):
            self.assertEqual(gather.mask(text), text)

    def test_a_quote_that_does_not_close_on_its_line_does_not_take_the_next_line_with_it(self):
        text = 'token: "\nthe next line is not a credential\n"'
        self.assertEqual(gather.mask(text), text)

    def test_a_credential_name_and_its_quote_cost_linear_time_even_when_the_quote_never_closes(self):
        # The second text is the worst case for testing a value against its closing quote at every
        # character: 3,000 keys, each opened by a longer run of backslashes than the next, so that none
        # is ever closed by a later one (4.5 million characters; 9 seconds if the run is not capped).
        import time
        worst = "".join("password: " + "\\" * n + '"' for n in range(3000, 0, -1))
        for text in ('password: "' + "word " * 60_000, worst):
            t0 = time.time()
            gather.mask(text)
            gather.mask_known(text)
            self.assertLess(time.time() - t0, 3.0, text[:20])

    def test_does_not_mask_what_only_looks_like_a_credential_name(self):
        for text in ("X25519Secret::generate(&mut OsRng)", "CancellationToken::new()", "InvalidPassword: failed to fill",
                     "token_count: 1234567", '"max_tokens": 4096', '"password": "abc"', "password-manager: enabled"):
            self.assertEqual(gather.mask(text), text)

    def test_the_writer_masks_every_line_it_writes_by_shape_and_leaves_pointers_alone(self):
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        token = "ghp_" + "a" * 30
        pointer = "rollout-2026-10-15T09-11-58-01a14055-5d49-7033-a5ee-9c4a77e02fa2.jsonl"  # long, mixed, and no secret
        target = tmp / "out.md"
        gather.write_text_private(target, f"a header with {token}\nraw log: {tmp}/{pointer}:12\n| cell | {{\"password\": \"hunter22\"}} |\n")
        written = target.read_text(encoding="utf-8")
        self.assertNotIn(token, written)
        self.assertNotIn("hunter22", written)
        self.assertIn(f"raw log: {tmp}/{pointer}:12", written)

    def test_the_writer_masks_a_long_random_run_in_a_path_but_not_what_a_pointer_is_made_of(self):
        tmp = Path(tempfile.mkdtemp(prefix="gather-test-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        half = "Zk9mQ2vDzX7bR4sT1pL8n"
        token = half * 2
        uuid = "0199abcd-ef01-7234-8bcd-0123456789ab"
        kept = [  # each is made of pointer shapes only, and must come through as it is
            f"/h/.claude/projects/-home-user-agent-tooling--claude-worktrees-heal-gather-2026-q3-roadmap/{uuid}.jsonl:12",
            f"/h/.codex/sessions/2026/10/15/rollout-2026-10-15T09-11-58-{uuid}.jsonl:1",
            f"/h/.gemini/tmp/{'a1b2c3d4' * 8}/chats/session-2026-10-15T10-00-abc12345.json#msg3",   # a sha256 project hash
            f"/h/.gemini/tmp/{'a1b2c3d4' * 5}/chats/s.json",                                           # a sha1
            f"/h/.claude/projects/-home-user/{uuid}/subagents/agent-a1b2c3d4e5f6a7b8.jsonl:3",
            f"/h/x/{'-' * 50}/{'a' * 50}/{'7' * 50}",                                                  # uniform runs are not tokens
            f"/h/a-long-prefix-name{uuid}.jsonl",                                                       # a UUID, whatever it is glued to
            "/h/a-long-prefix-name-for-the-run-2026-10-15T09-11-58.log",                                # a date and time, after a long name
            "/h/agent-a1b2c3d4e5f6a7b8-c9d0e1f2a3b4c5d6-e7f8a9b0c1d2e3f4.jsonl",                        # hex ids, joined
        ]
        masked = {  # a token-shaped run, or a pointer shape joined to one, goes
            f"/h/{token}/a.jsonl:1": "/h/[masked]/a.jsonl:1",
            f"/h/-home-user-{token}/b.jsonl": "/h/[masked]/b.jsonl",
            f"/h/{half}-{half}/c.jsonl": "/h/[masked]/c.jsonl",
            f"/h/{uuid}-{token}/d.jsonl": "/h/[masked]/d.jsonl",
            f"/h/rollout-2026-10-15T09-11-58-{token}.jsonl": "/h/[masked].jsonl",
            f"/h/{'a1b2c3d4' * 6}/e.jsonl": "/h/[masked]/e.jsonl",                                      # 48 hex: not a sha
            f"/h/{half}a1b2c3d4e5f6a7b8{half}/f.jsonl": "/h/[masked]/f.jsonl",                           # hex inside a token is not an id
        }
        target = tmp / "out.md"
        gather.write_text_private(target, "\n".join(kept + list(masked)) + "\n")
        self.assertEqual(target.read_text(encoding="utf-8").split("\n")[:-1], kept + list(masked.values()))

    def test_masking_by_shape_is_the_full_masker_less_its_catch_all(self):
        for text in ("plain words", "Authorization: Bearer abc123def456ghi", "postgres://admin:S3cr3tPassw0rd@host/db",
                     "see sk-" + "a1b2c3d4e5f6a7b8", "x" * 5000, 'a "token": "abcdef123456" b', "TOKEN: abcdef123456",
                     "https://example.com/path", "a basic outline", "bearer authentication"):
            unfiltered = gather.SPECIFIC_SECRETS.sub("[masked]", gather.URL_CREDS.sub(r"\1[masked]@", text))
            self.assertEqual(gather.mask_known(text), unfiltered, text)

    def test_masks_url_userinfo_credentials(self):
        out = gather.mask("postgres://admin:S3cr3tPassw0rd@host/db")
        self.assertNotIn("S3cr3tPassw0rd", out)
        self.assertIn("postgres://", out)
        self.assertIn("@host/db", out)

    def test_mask_is_not_quadratic_on_a_long_uniform_run(self):
        # A long run of one repeated character (padding, separators, a progress bar) is
        # ordinary build output, not a secret -- and unlike a real secret it has no short
        # literal anchor, so a lookahead- or backtracking-prone pattern degrades to O(n^2) on
        # it specifically. 300k chars comfortably reproduces the multi-second-per-10k blowup
        # this regresses without making a slow test suite even when the fix regresses.
        import time
        for masker in (gather.mask, gather.mask_written):
            for text in ("a" * 300_000, "-" * 300_000, "7" * 300_000, "a1b2c3d4-" * 40_000):
                t0 = time.time()
                masker(text)
                elapsed = time.time() - t0
                self.assertLess(elapsed, 3.0, f"{masker.__name__}() took {elapsed:.2f}s on a uniform run (quadratic regression)")

    def test_trim_bounds_masking_cost_regardless_of_input_size(self):
        import time
        huge = "z" * 5_000_000
        t0 = time.time()
        out = gather.trim(huge, 2000, "file:1")
        elapsed = time.time() - t0
        self.assertLess(elapsed, 3.0, f"trim() took {elapsed:.2f}s on a 5M-char input")
        self.assertLessEqual(len(out), 2000 + len("... [trimmed; full text at file:1]"))

    def test_url_creds_does_not_leak_a_secret_that_straddles_the_trim_cutoff(self):
        # A generic (unprefixed) secret starting well before the cutoff must still be masked
        # even though it, or the text after it, gets cut off by --max-chars.
        text = "prefix " + ("k9mQ2vDzX7bR4sT1pL8n" * 3) + " suffix"  # 60+ chars, digits+letters
        out = gather.trim(text, limit=20, ref="file:1")
        self.assertIn("[masked]", out)


class LaunchdAgentsTest(unittest.TestCase):
    """launchd_agents() only runs its real logic on darwin; sys.platform and Path.home are
    patched to exercise that logic on this (Linux) machine, the way the drift/portability
    reviews did to reach macOS-only code without a Mac."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="launchd-test-"))
        self.agents_dir = self.tmp / "Library" / "LaunchAgents"
        self.agents_dir.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        import unittest.mock as mock
        with mock.patch.object(gather.sys, "platform", "darwin"), \
             mock.patch.object(gather.Path, "home", return_value=self.tmp):
            return gather.launchd_agents()

    def test_truncated_plist_is_a_note_not_a_crash(self):
        (self.agents_dir / "broken.plist").write_bytes(b"<?xml version=\"1.0\"?><plist><dict><key>Label")
        rows, err = self._run()
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertIn("unreadable plist", rows[0])

    def test_plist_whose_root_is_an_array_is_a_note_not_a_crash(self):
        import plistlib
        (self.agents_dir / "array-root.plist").write_bytes(plistlib.dumps(["not", "a", "dict"]))
        rows, err = self._run()
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertIn("unexpected plist shape", rows[0])

    def test_well_formed_plist_is_still_read_normally(self):
        import plistlib
        (self.agents_dir / "ok.plist").write_bytes(plistlib.dumps({"Label": "com.example.job", "StartInterval": 3600}))
        rows, err = self._run()
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertIn("com.example.job", rows[0])


class PureFunctionTest(unittest.TestCase):
    def test_safe_name_coerces_non_string_ids(self):
        self.assertEqual(gather.safe_name(12345), "12345")
        self.assertEqual(gather.safe_name(None), "unknown")

    def test_rel_or_abs_does_not_conflate_sibling_directories(self):
        home = str(Path.home())
        self.assertEqual(gather.rel_or_abs(Path(home)), "~")
        self.assertEqual(gather.rel_or_abs(Path(home + "/sub")), "~/sub")
        # A sibling directory that merely starts with the same characters as $HOME must not be
        # rendered as if it were under $HOME.
        self.assertEqual(gather.rel_or_abs(Path(home + "-other/project")), home + "-other/project")

    def test_parse_when_accepts_trailing_z_and_keeps_a_given_offset(self):
        z = gather.parse_when("2026-01-01T00:00:00Z")
        self.assertEqual(z, gather.dt.datetime(2026, 1, 1, tzinfo=gather.UTC))
        offset = gather.parse_when("2026-01-01T05:00:00+05:00")
        self.assertEqual(offset.astimezone(gather.UTC), gather.dt.datetime(2026, 1, 1, tzinfo=gather.UTC))

    def test_parse_when_rejects_garbage_with_a_clean_error_not_a_traceback(self):
        with self.assertRaises(SystemExit):
            gather.parse_when("not-a-date")


if __name__ == "__main__":
    unittest.main()
