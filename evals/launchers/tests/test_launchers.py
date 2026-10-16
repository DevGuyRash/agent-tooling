"""The record each launcher builds from its executor's own output (see ../README.md), checked on hand-written events
in each executor's format, with every expected value worked out by hand from the events themselves."""
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(f"launcher_{name}", HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


codex, claude = load("codex"), load("claude")


def command_item(item_id, command, code, output):
    return {"id": item_id, "type": "command_execution", "command": command, "aggregated_output": output,
            "exit_code": code, "status": "completed" if code == 0 else "failed"}


class CodexRecordTest(unittest.TestCase):
    def test_usage_is_the_last_running_total_and_actions_take_their_start_order(self):
        turn1 = [{"type": "thread.started", "thread_id": "T1"}, {"type": "turn.started"},
                 {"type": "item.started", "item": command_item("a", "sleep 2", None, "")},
                 {"type": "item.started", "item": command_item("b", "ls", None, "")},
                 {"type": "item.completed", "item": command_item("b", "ls", 0, "out.txt\n")},
                 {"type": "item.completed", "item": command_item("a", "sleep 2", 0, "")},
                 {"type": "item.started", "item": {"id": "c", "type": "file_change", "changes": [{"path": "src/x.py"}], "status": "in_progress"}},
                 {"type": "item.completed", "item": {"id": "c", "type": "file_change", "changes": [{"path": "src/x.py"}], "status": "completed"}},
                 {"type": "item.completed", "item": {"id": "d", "type": "agent_message", "text": "done"}},
                 {"type": "turn.completed", "usage": {"input_tokens": 1000, "cached_input_tokens": 600, "output_tokens": 80,
                                                       "reasoning_output_tokens": 30}}]
        turn2 = [{"type": "turn.started"},
                 {"type": "item.completed", "item": {"id": "a", "type": "agent_message", "text": "nothing else"}},
                 {"type": "turn.completed", "usage": {"input_tokens": 2500, "cached_input_tokens": 1900, "output_tokens": 120,
                                                       "reasoning_output_tokens": 45}}]
        rollout = [{"type": "session_meta", "payload": {"id": "T1"}},
                   {"type": "turn_context", "payload": {"model": "model-a", "effort": "medium"}}]
        record = codex.record_from([turn1, turn2], [rollout], True, "/tmp/run/work")
        self.assertTrue(record["finished"])
        # turn.completed is a running total for the thread: the second turn's numbers are the whole run's
        self.assertEqual(record["usage"], {"input_tokens": 2500, "cached_input_tokens": 1900, "output_tokens": 120,
                                           "reasoning_tokens": 45})
        self.assertEqual([(a["kind"], a.get("command") or a.get("path") or a.get("text")) for a in record["actions"]],
                         [("command", "sleep 2"), ("command", "ls"), ("edit", "src/x.py"), ("message", "done"),
                          ("message", "nothing else")])
        self.assertEqual([a["turn"] for a in record["actions"]], [1, 1, 1, 1, 2])
        self.assertEqual(record["actions"][1]["output"], "out.txt\n")
        self.assertEqual(record["turns"], [{"session": "T1", "model": "model-a", "instructions": "system", "cwd": "/tmp/run/work"}] * 2)

    def test_a_failed_turn_is_not_finished(self):
        record = codex.record_from([[{"type": "thread.started", "thread_id": "T"}, {"type": "turn.failed", "error": {}}]], [], False, "/w")
        self.assertFalse(record["finished"])
        self.assertNotIn("usage", record)

    def test_subagent_commands_and_skill_injections_come_from_their_own_rollouts(self):
        main = [{"type": "session_meta", "payload": {"id": "T1"}},
                {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": "<skill>\n<name>deploy-helper</name>\n...</skill>"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "developer", "content": [
                    {"type": "input_text", "text": "<skills_instructions>\n- deploy-helper: Deploys it. (file: /h/.agents/skills/deploy-helper/SKILL.md)\n"
                                                   "- quiet (file: /h/.agents/skills/quiet/SKILL.md)\n</skills_instructions>"}]}}]
        # A subagent's rollout names its own thread first, then repeats its parent's session_meta.
        sub = [{"type": "session_meta", "payload": {"id": "S1"}}, {"type": "session_meta", "payload": {"id": "T1"}},
               {"type": "event_msg", "payload": {"type": "item_completed", "item": {
                   "type": "CommandExecution", "command": ["/bin/sh", "-lc", "cat SKILL.md"], "exit_code": 0,
                   "aggregated_output": "---\nname: deploy-helper\n---\nbody"}}}]
        record = codex.record_from([[{"type": "thread.started", "thread_id": "T1"}]], [main, sub], False, "/w")
        loads = [a for a in record["actions"] if a["kind"] == "load"]
        self.assertEqual([(a["name"], a.get("agent")) for a in loads], [("deploy-helper", None)])
        sub_commands = [a for a in record["actions"] if a.get("agent") == "S1"]
        self.assertEqual([(a["command"], a["ok"]) for a in sub_commands], [("/bin/sh -lc cat SKILL.md", True)])
        self.assertEqual(record["listed"], {"deploy-helper": "Deploys it.", "quiet": ""})

    def test_setup_keeps_only_the_provider_block_of_this_machines_configuration(self):
        host = ('model = "x"\nmodel_provider = "proxy"\n[mcp_servers.one]\ncommand = "server"\n'
                '[model_providers.proxy]\nbase_url = "https://proxy.example/v1"\nenv_key = "PROXY_KEY"\n')
        config = codex.provider_config("model-a", "low", host)
        self.assertIn('model = "model-a"', config)
        self.assertIn('model_reasoning_effort = "low"', config)
        self.assertIn('model_provider = "proxy"', config)
        self.assertIn('base_url = "https://proxy.example/v1"', config)
        self.assertNotIn("mcp_servers", config)
        self.assertIn("plugins = false", config)


class ClaudeRecordTest(unittest.TestCase):
    def turn(self, session, uses, results, text, usage, cost, model="model-c"):
        events = [{"type": "system", "subtype": "init", "session_id": session, "model": model, "cwd": "/tmp/run/work"}]
        events.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": i, "name": n, "input": inp}
                                                                    for i, n, inp in uses]}})
        events.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "is_error": err,
                                                               "content": out} for i, err, out in results]}})
        events.append({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
        events.append({"type": "result", "subtype": "success", "is_error": False, "session_id": session, "usage": usage,
                       "total_cost_usd": cost, "modelUsage": {model: {}}, "result": text})
        return events

    def test_usage_adds_cache_reads_and_writes_to_input_and_sums_the_turns(self):
        t1 = self.turn("S", [("u1", "Bash", {"command": "pytest -q"}), ("u2", "Read", {"file_path": "/h/skills/x/SKILL.md"}),
                             ("u3", "Edit", {"file_path": "src/a.py"}), ("u4", "Skill", {"skill": "plug:x"}),
                             ("u5", "Grep", {"pattern": "def"})],
                       [("u1", True, "1 failed"), ("u2", False, "---\nname: x\n---"), ("u3", False, "ok"), ("u4", False, "loaded"),
                        ("u5", False, [{"type": "text", "text": "a.py:1"}])],
                       "first", {"input_tokens": 10, "cache_read_input_tokens": 900, "cache_creation_input_tokens": 90,
                                 "output_tokens": 50, "output_tokens_details": {"thinking_tokens": 20}}, 0.05)
        t2 = self.turn("S", [], [], "second", {"input_tokens": 5, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0,
                                                "output_tokens": 30, "output_tokens_details": {"thinking_tokens": 0}}, 0.08)
        record = claude.record_from([t1, t2], [], True)
        # per-turn usage summed: input 10+900+90 + 5+1000+0, cached 900+1000, output 50+30, thinking 20+0; cost is a running total
        self.assertEqual(record["usage"], {"input_tokens": 2005, "cached_input_tokens": 1900, "output_tokens": 80,
                                           "reasoning_tokens": 20, "cost_usd": 0.08})
        kinds = [(a["kind"], a.get("ok")) for a in record["actions"]]
        self.assertEqual(kinds, [("command", False), ("read", True), ("edit", True), ("load", True), ("other", True),
                                 ("message", None), ("message", None)])
        self.assertEqual(record["actions"][3]["name"], "plug:x")
        self.assertEqual(record["actions"][4]["output"], "a.py:1")
        self.assertEqual([t["session"] for t in record["turns"]], ["S", "S"])
        self.assertEqual(record["turns"][0]["model"], "model-c")
        self.assertTrue(record["finished"])

    def test_the_listing_comes_from_skill_listing_attachments(self):
        transcript = [{"attachment": {"type": "skill_listing", "content": "- helper: Helps.\n- quiet", "names": ["helper", "quiet"]}}]
        record = claude.record_from([[]], transcript, False)
        self.assertEqual(record["listed"], {"helper": "Helps.", "quiet": ""})
        self.assertFalse(record["finished"])
        self.assertEqual(claude.record_from([[]], [], False).get("listed"), None)


if __name__ == "__main__":
    unittest.main()
