"""What gather.py extracts from each host's native logs, faithfully and without interpretation."""
import importlib.util
import json
import os
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
        g = lambda *a: subprocess.run(["git", "-C", str(self.repo), *a], capture_output=True, check=True, text=True)
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
        env = dict(os.environ)
        env.pop("CODEX_HOME", None)
        env.pop("CLAUDE_CONFIG_DIR", None)
        if extra_env:
            env.update(extra_env)
        args = [sys.executable, str(SCRIPT)]
        if since is not None:
            args += ["--since", since]
        if out is not None:
            args += ["--out", str(out)]
        args += list(extra_args)
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env=env)

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
        # the unrecognized item type and unrecognized top-level type are noted, not dropped
        self.assertIn("FutureItemType", codex_main)
        self.assertIn("brand_new_top_level_record", codex_main)
        self.assertEqual(codex_main.count("] note:"), 2)
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
        for text in ("a" * 300_000, "-" * 300_000, "7" * 300_000):
            t0 = time.time()
            gather.mask(text)
            elapsed = time.time() - t0
            self.assertLess(elapsed, 3.0, f"mask() took {elapsed:.2f}s on a uniform run (quadratic regression)")

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
