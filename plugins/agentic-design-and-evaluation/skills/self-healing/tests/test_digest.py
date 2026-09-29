"""Facts the digest extracts from each harness's native logs and from repository state."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "digest.py"
sys.path.insert(0, str(SCRIPT.parent))
import digest  # noqa: E402


def jl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def item(ts, it):
    return {"timestamp": ts, "type": "event_msg", "payload": {"type": "item_completed", "item": it}}


def text(t):
    return [{"type": "text", "text": t}]


class DigestTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="digest-test-"))
        jl(self.root / "codex" / "2026" / "09" / "28" / "rollout-a.jsonl", [
            {"timestamp": "2026-09-28T10:00:00Z", "type": "session_meta", "payload": {"id": "codex-a", "cwd": "/repo/app"}},
            item("2026-09-28T10:00:01Z", {"type": "UserMessage", "content": text("<environment_context>x</environment_context>")}),
            item("2026-09-28T10:00:02Z", {"type": "UserMessage", "content": text("Fix the build and open a PR")}),
            item("2026-09-28T10:01:00Z", {"type": "CommandExecution", "command": ["/usr/bin/zsh", "-lc", "git worktree add ../wt -b fix"], "exit_code": 0}),
            item("2026-09-28T10:02:00Z", {"type": "CommandExecution", "command": ["/usr/bin/zsh", "-lc", "python3 -m pytest -q"], "exit_code": 1}),
            item("2026-09-28T10:03:00Z", {"type": "CommandExecution", "command": ["/usr/bin/zsh", "-lc", "gh pr create --fill"], "exit_code": 0}),
            item("2026-09-28T10:04:00Z", {"type": "CommandExecution", "command": ["/usr/bin/zsh", "-lc", "cat plugins/x/skills/tdd/SKILL.md"], "exit_code": 0}),
            {"timestamp": "2026-09-28T10:05:00Z", "type": "compacted", "payload": {"message": "summary"}},
            item("2026-09-28T10:06:00Z", {"type": "AgentMessage", "content": text("Opened two PRs, one per file.")}),
            item("2026-09-28T11:00:00Z", {"type": "UserMessage", "content": text("No, I said one PR only")}),
            item("2026-09-28T11:30:00Z", {"type": "AgentMessage", "content": text("Consolidated into one PR.")}),
            item("2026-09-28T11:31:00Z", {"type": "UserMessage", "content": text("continue")}),
            item("2026-09-28T11:40:00Z", {"type": "UserMessage", "content": text("<heartbeat>keep going until the objective is complete</heartbeat>")}),
            {"timestamp": "2026-09-28T12:00:01Z", "type": "event_msg", "payload": {"type": "token_count"}},
        ])
        jl(self.root / "claude" / "proj" / "b.jsonl", [
            {"timestamp": "2026-09-28T10:00:00Z", "type": "user", "cwd": "/repo/app", "message": {"content": "Run the tests"}},
            {"timestamp": "2026-09-28T10:01:00Z", "type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "python3 -m pytest -q"}}]}},
            {"timestamp": "2026-09-28T10:01:05Z", "type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "fail"}]}},
            {"timestamp": "2026-09-28T10:02:00Z", "type": "assistant", "message": {"content": [{"type": "text", "text": "Tests fail."}]}},
        ])
        gem = self.root / "gemini" / "hash" / "chats" / "session-1.json"
        gem.parent.mkdir(parents=True)
        gem.write_text(json.dumps({"sessionId": "gem-1", "startTime": "2026-09-28T10:00:00Z", "lastUpdated": "2026-09-28T10:10:00Z", "messages": [
            {"type": "user", "content": "Build it", "timestamp": "2026-09-28T10:00:00Z"},
            {"type": "gemini", "content": "ok", "timestamp": "2026-09-28T10:01:00Z",
             "toolCalls": [{"name": "run_shell_command", "args": {"command": "python3 -m pytest -q"}, "status": "error"}]}]}))
        self.repo = self.root / "repos" / "app"
        self.repo.mkdir(parents=True)
        g = lambda *a: subprocess.run(["git", "-C", str(self.repo), *a], capture_output=True, check=True)
        g("init", "-q", "-b", "main")
        (self.repo / "f").write_text("x")
        g("add", "f")
        g("-c", "user.name=a", "-c", "user.email=a@b", "commit", "-qm", "init")
        g("branch", "done-feature")
        g("worktree", "add", "-q", str(self.root / "repos" / "app-wt"), "-b", "stale")

    def tearDown(self):
        subprocess.run(["rm", "-rf", str(self.root)])

    def run_digest(self, *extra):
        r = subprocess.run([sys.executable, str(SCRIPT), "--codex", str(self.root / "codex"), "--claude", str(self.root / "claude"),
                            "--gemini", str(self.root / "gemini"), "--repos", str(self.root / "repos"), "--since", "2026-09-01",
                            *(["--automations", str(self.root / "none")] if "--automations" not in extra else []), *extra],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_codex_thread_facts_skip_injected_context_and_count_heartbeats(self):
        d = json.loads(self.run_digest("--json"))
        f = next(t for t in d["threads"] if t["host"] == "codex")
        self.assertEqual(f["user_messages"], 3)
        self.assertEqual((f["corrections"], f["nudges"], f["heartbeats"]), (1, 1, 1))
        self.assertEqual((f["worktrees_added"], f["prs_created"], f["compactions"], f["failed_commands"]), (1, 1, 1, 1))

    def test_corrections_are_paired_with_the_agent_message_before_them(self):
        d = json.loads(self.run_digest("--json"))
        sig = next(s for s in d["signals"] if s["kind"] == "correction")
        self.assertEqual(sig["user"], "No, I said one PR only")
        self.assertEqual(sig["before"], "Opened two PRs, one per file.")

    def test_failures_are_counted_by_distinct_sessions_across_hosts(self):
        shapes = {r["shape"]: r for r in json.loads(self.run_digest("--json"))["failing_shapes"]}
        self.assertEqual((shapes["python3 -m pytest"]["sessions"], shapes["python3 -m pytest"]["failures"]), (3, 3))

    def test_reports_skill_reads_and_repository_residue(self):
        d = json.loads(self.run_digest("--json"))
        self.assertIn("tdd", {r["skill"] for r in d["instructions_read"]})
        res = next(r for r in d["residue"] if r["repo"].endswith("/app"))
        self.assertEqual((res["extra_worktrees"], res["merged_but_present"] >= 1), (1, True))

    def test_lists_automations_with_their_stop_clause(self):
        auto = self.root / "automations" / "keepalive"
        auto.mkdir(parents=True)
        (auto / "automation.toml").write_text('id = "keepalive"\nkind = "heartbeat"\nstatus = "ACTIVE"\n'
                                              'rrule = "RRULE:FREQ=HOURLY"\ncreated_at = 1790000000000\n'
                                              'prompt = "Resume the task. Keep going until the requested work is complete."\n')
        d = json.loads(self.run_digest("--json", "--automations", str(self.root / "automations")))
        a = d["automations"][0]
        self.assertEqual((a["id"], a["status"]), ("keepalive", "ACTIVE"))
        self.assertIn("until the requested work is complete", a["stop_clause"])

    def test_show_prints_one_session_around_a_time(self):
        out = self.run_digest("show", "codex-a", "--at", "2026-09-28T11:00:00Z", "--context", "1")
        self.assertIn("No, I said one PR only", out)

    def test_command_shapes_keep_the_program_and_drop_values(self):
        self.assertEqual(digest.shape('/usr/bin/zsh -lc "cd /x && python3 scripts/check.py --all"'), "python3 check.py")
        self.assertEqual(digest.shape("FOO=1 git status --short"), "git status")
        self.assertEqual(digest.shape("./scripts/install-all --dry-run"), "install-all")

    def test_masks_token_like_strings(self):
        self.assertNotIn("ghp_" + "a" * 30, digest.mask("token ghp_" + "a" * 30 + " here", 200))


if __name__ == "__main__":
    unittest.main()
