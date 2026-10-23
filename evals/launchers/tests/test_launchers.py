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


class CodexAccountTest(unittest.TestCase):
    def test_a_signed_in_account_brings_none_of_its_apps_plugins_suggestions_or_memories(self):
        # A ChatGPT login's account-scoped features, as Codex's own feature table names them (codex-rs/features/src/
        # lib.rs at rust-v0.163.0): apps, plugins, the remote plugin catalog and its sharing flows, recommended plugins
        # in the model's context, app tool suggestions, and memories; each is turned off in the run's private
        # configuration, whatever login it holds, and nothing else there is a feature.
        import tomllib
        features = tomllib.loads(codex.provider_config("model-a", "low", ""))["features"]
        self.assertEqual(features, {"apps": False, "plugins": False, "remote_plugin": False, "plugin_sharing": False,
                                    "recommended_plugins": False, "tool_suggest": False, "memories": False})


class CodexTimelineTest(unittest.TestCase):
    def test_injected_skills_unfinished_commands_and_subagents_keep_their_turn_and_place(self):
        turn1 = [{"type": "thread.started", "thread_id": "T1"},
                 {"type": "item.started", "item": command_item("a", "sleep 99", None, "")},
                 {"type": "item.started", "item": {"id": "c", "type": "collab_tool_call", "receiver_thread_ids": ["S1"], "status": "in_progress"}},
                 {"type": "item.completed", "item": {"id": "c", "type": "collab_tool_call", "receiver_thread_ids": ["S1"], "status": "completed"}},
                 {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 1}}]
        turn2 = [{"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": "second"}},
                 {"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 2}}]
        main = [{"type": "session_meta", "payload": {"id": "T1"}},
                {"type": "event_msg", "payload": {"type": "task_started"}},
                {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": "<skill><name>deploy-helper</name></skill>"}]}},
                {"type": "event_msg", "payload": {"type": "task_started"}}]
        sub = [{"type": "session_meta", "payload": {"id": "S1"}}, {"type": "session_meta", "payload": {"id": "T1"}},
               {"type": "event_msg", "payload": {"type": "item_completed", "item": {
                   "type": "CommandExecution", "command": ["sh", "-lc", "cat x"], "exit_code": 0, "aggregated_output": "o"}}}]
        record = codex.record_from([turn1, turn2], [main, sub], False, "/w")
        shown = [(a["turn"], a["kind"], a.get("name") or a.get("command") or a.get("text"), a.get("ok"), a.get("agent"))
                 for a in record["actions"]]
        self.assertEqual(shown, [(1, "load", "deploy-helper", True, None), (1, "command", "sleep 99", None, None),
                                 (1, "other", "collab_tool_call", True, None), (1, "command", "sh -lc cat x", True, "S1"),
                                 (2, "message", "second", None, None)])


class CodexSubagentTurnTest(unittest.TestCase):
    def test_a_subagent_started_in_one_turn_and_awaited_in_the_next_keeps_each_command_in_its_own_turn(self):
        spawn = {"id": "s", "type": "collab_tool_call", "tool": "spawn_agent", "receiver_thread_ids": ["S1"], "status": "completed"}
        wait = {"id": "w", "type": "collab_tool_call", "tool": "wait", "receiver_thread_ids": ["S1"], "status": "completed"}
        turn1 = [{"type": "thread.started", "thread_id": "T1"}, {"type": "item.completed", "item": spawn},
                 {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": "first"}},
                 {"type": "turn.completed", "usage": {}}]
        turn2 = [{"type": "item.completed", "item": wait}, {"type": "turn.completed", "usage": {}}]
        main = [{"type": "session_meta", "payload": {"id": "T1"}},
                {"type": "event_msg", "timestamp": "2026-10-16T10:00:00Z", "payload": {"type": "task_started"}},
                {"type": "event_msg", "timestamp": "2026-10-16T10:05:00Z", "payload": {"type": "task_started"}}]
        command = lambda at, text: {"type": "event_msg", "timestamp": at, "payload": {"type": "item_completed", "item": {
            "type": "CommandExecution", "command": text, "exit_code": 0, "aggregated_output": ""}}}
        sub = [{"type": "session_meta", "payload": {"id": "S1"}}, {"type": "session_meta", "payload": {"id": "T1"}},
               command("2026-10-16T10:01:00Z", "early"), command("2026-10-16T10:06:00Z", "late")]
        record = codex.record_from([turn1, turn2], [main, sub], False, "/w")
        shown = [(a["turn"], a.get("command") or a.get("name") or a.get("text"), a.get("agent")) for a in record["actions"]]
        self.assertEqual(shown, [(1, "spawn_agent", None), (1, "early", "S1"), (1, "first", None), (2, "wait", None),
                                 (2, "late", "S1")])

    def test_a_subagents_actions_take_the_turn_and_place_in_which_they_started(self):
        # Turn 1 began at 10:00:00 and turn 2 at 10:05:00. The subagent's command was called at 10:04:00 and completed
        # at 10:06:00, so it belongs to turn 1, between the main agent's command "a" (10:00:20) and "b" (started at
        # 10:04:48, two seconds before it completed); its skill (10:06:30), message (10:07:00) and the command it
        # called at 10:07:10 and never finished come after the main agent's turn-2 message (10:05:10).
        spawn = {"id": "s", "type": "collab_tool_call", "tool": "spawn_agent", "receiver_thread_ids": ["S1"], "status": "completed"}
        turn1 = [{"type": "thread.started", "thread_id": "T1"}, {"type": "item.completed", "item": spawn},
                 {"type": "item.completed", "item": command_item("i1", "a", 0, "")},
                 {"type": "item.completed", "item": command_item("i2", "b", 0, "")}, {"type": "turn.completed", "usage": {}}]
        turn2 = [{"type": "item.completed", "item": {"id": "i3", "type": "agent_message", "text": "second"}},
                 {"type": "turn.completed", "usage": {}}]
        event = lambda at, payload: {"type": "event_msg", "timestamp": at, "payload": payload}
        done = lambda at, item: event(at, {"type": "item_completed", "item": item})
        main = [{"type": "session_meta", "payload": {"id": "T1"}},
                event("2026-10-16T10:00:00Z", {"type": "task_started"}),
                done("2026-10-16T10:00:10Z", {"type": "CollabAgentToolCall", "tool": "spawn_agent"}),
                done("2026-10-16T10:00:20Z", {"type": "CommandExecution", "command": ["sh", "-c", "a"], "duration": {"secs": 0, "nanos": 0}}),
                done("2026-10-16T10:04:50Z", {"type": "CommandExecution", "command": ["sh", "-c", "b"], "duration": {"secs": 2, "nanos": 0}}),
                event("2026-10-16T10:05:00Z", {"type": "task_started"}),
                done("2026-10-16T10:05:10Z", {"type": "AgentMessage", "content": [{"type": "Text", "text": "second"}]})]
        call = lambda at, call_id, cmd: {"type": "response_item", "timestamp": at, "payload": {
            "type": "function_call", "name": "exec_command", "call_id": call_id, "arguments": '{"cmd": "%s"}' % cmd}}
        sub = [{"type": "session_meta", "payload": {"id": "S1"}}, {"type": "session_meta", "payload": {"id": "T1"}},
               done("2026-10-16T10:00:30Z", {"type": "FileChange", "id": "e1", "status": "completed",
                                             "changes": {"/w/notes.md": {"type": "update"}}}),
               call("2026-10-16T10:04:00Z", "k1", "slow"),
               done("2026-10-16T10:06:00Z", {"type": "CommandExecution", "id": "k1", "command": ["sh", "-c", "slow"],
                                             "exit_code": 0, "aggregated_output": "out"}),
               {"type": "response_item", "timestamp": "2026-10-16T10:06:30Z", "payload": {
                   "type": "message", "role": "user", "content": [{"type": "input_text", "text": "<skill>\n<name>helper</name>\n</skill>"}]}},
               done("2026-10-16T10:07:00Z", {"type": "AgentMessage", "content": [{"type": "Text", "text": "done"}]}),
               call("2026-10-16T10:07:10Z", "k2", "pending")]
        record = codex.record_from([turn1, turn2], [main, sub], False, "/w")
        shown = [(a["turn"], a["kind"], a.get("command") or a.get("name") or a.get("text") or a.get("path"), a.get("ok"),
                  a.get("agent")) for a in record["actions"]]
        self.assertEqual(shown, [(1, "other", "spawn_agent", True, None), (1, "command", "a", True, None),
                                 (1, "edit", "/w/notes.md", True, "S1"), (1, "command", "sh -c slow", True, "S1"),
                                 (1, "command", "b", True, None), (2, "message", "second", None, None),
                                 (2, "load", "helper", True, "S1"), (2, "message", "done", None, "S1"),
                                 (2, "command", "pending", None, "S1")])


    def test_an_unfinished_main_command_takes_no_other_commands_time(self):
        # Turn 1's "pending" never completed, so the rollout holds no time for it: "middle" keeps its own 10:05:10 and
        # the subagent's command at 10:06 comes after it in turn 2, before turn 3's "last".
        spawn = {"id": "s", "type": "collab_tool_call", "tool": "spawn_agent", "receiver_thread_ids": ["S1"], "status": "completed"}
        turn1 = [{"type": "thread.started", "thread_id": "T1"}, {"type": "item.completed", "item": spawn},
                 {"type": "item.started", "item": command_item("p", "pending", None, "")}, {"type": "turn.completed", "usage": {}}]
        turn2 = [{"type": "item.completed", "item": command_item("m", "middle", 0, "")}, {"type": "turn.completed", "usage": {}}]
        turn3 = [{"type": "item.completed", "item": command_item("l", "last", 0, "")}, {"type": "turn.completed", "usage": {}}]
        event = lambda at, payload: {"type": "event_msg", "timestamp": at, "payload": payload}
        done = lambda at, command: event(at, {"type": "item_completed", "item": {
            "type": "CommandExecution", "command": ["sh", "-c", command], "exit_code": 0, "duration": {"secs": 0, "nanos": 0}}})
        main = [{"type": "session_meta", "payload": {"id": "T1"}},
                event("2026-10-16T10:00:00Z", {"type": "task_started"}),
                event("2026-10-16T10:05:00Z", {"type": "task_started"}), done("2026-10-16T10:05:10Z", "middle"),
                event("2026-10-16T10:10:00Z", {"type": "task_started"}), done("2026-10-16T10:10:10Z", "last")]
        sub = [{"type": "session_meta", "payload": {"id": "S1"}}, {"type": "session_meta", "payload": {"id": "T1"}},
               done("2026-10-16T10:06:00Z", "sub")]
        record = codex.record_from([turn1, turn2, turn3], [main, sub], False, "/w")
        shown = [(a["turn"], a.get("command") or a.get("name"), a.get("ok"), a.get("agent")) for a in record["actions"]]
        self.assertEqual(shown, [(1, "spawn_agent", True, None), (1, "pending", None, None), (2, "middle", True, None),
                                 (2, "sh -c sub", True, "S1"), (3, "last", True, None)])


class ClaudeRecordTest(unittest.TestCase):
    def test_a_subagents_actions_carry_the_call_that_started_it(self):
        events = [{"type": "system", "subtype": "init", "session_id": "S", "model": "m"},
                  {"type": "assistant", "parent_tool_use_id": "task1", "message": {"content": [
                      {"type": "tool_use", "id": "u1", "name": "Bash", "input": {"command": "ls"}}]}},
                  {"type": "assistant", "message": {"content": [{"type": "text", "text": "main"}]}},
                  {"type": "result", "subtype": "success", "is_error": False, "session_id": "S", "usage": {}}]
        record = claude.record_from([events], [], False)
        self.assertEqual([(a["kind"], a.get("agent")) for a in record["actions"]], [("command", "task1"), ("message", None)])

    def test_a_subagents_calls_only_its_transcript_holds_are_its_actions_in_their_turn(self):
        stream = [[{"type": "system", "subtype": "init", "session_id": "S"},
                   {"type": "result", "subtype": "success", "is_error": False, "session_id": "S", "usage": {}}],
                  [{"type": "result", "subtype": "success", "is_error": False, "session_id": "S", "usage": {}}]]
        transcript = [{"type": "user", "timestamp": "2026-10-16T10:00:00Z", "message": {"content": "first prompt"}},
                      {"type": "assistant", "isSidechain": True, "agentId": "A1", "timestamp": "2026-10-16T10:01:00Z",
                       "message": {"content": [{"type": "tool_use", "id": "c1", "name": "Bash", "input": {"command": "echo child"}}]}},
                      {"type": "user", "isSidechain": True, "message": {"content": [
                          {"type": "tool_result", "tool_use_id": "c1", "is_error": False, "content": "child"}]}},
                      {"type": "user", "timestamp": "2026-10-16T10:05:00Z", "message": {"content": "second prompt"}}]
        record = claude.record_from(stream, transcript, False)
        self.assertEqual([(a["turn"], a["kind"], a.get("command"), a.get("ok"), a.get("agent")) for a in record["actions"]],
                         [(1, "command", "echo child", True, "A1")])
        self.assertNotIn("id", record["actions"][0])

    def test_what_only_a_subagents_transcript_holds_takes_its_place_by_time_and_its_messages_count(self):
        # The stream showed the Task call (10:00:05), the subagent's own streamed message (10:00:15) and the parent's
        # messages (10:00:20, then 10:05:05 in turn 2). Only the transcript holds the subagent's 10:00:10 message and
        # command, so they come right after the Task call; its streamed message is not repeated.
        assistant = lambda uuid, content, **extra: {"type": "assistant", "uuid": uuid, "message": {"id": "m" + uuid, "content": content}, **extra}
        result = {"type": "result", "subtype": "success", "is_error": False, "session_id": "S", "usage": {}}
        stream = [[{"type": "system", "subtype": "init", "session_id": "S"},
                   assistant("e1", [{"type": "tool_use", "id": "t1", "name": "Task", "input": {}}]),
                   assistant("e4", [{"type": "text", "text": "streamed child"}], parent_tool_use_id="t1"),
                   assistant("e2", [{"type": "text", "text": "parent one"}]), result],
                  [assistant("e3", [{"type": "text", "text": "parent two"}]), result]]
        at = lambda second: f"2026-10-16T10:{second}Z"
        transcript = [{"type": "user", "timestamp": at("00:00"), "message": {"content": "first prompt"}},
                      dict(assistant("e1", []), timestamp=at("00:05")),
                      {"type": "assistant", "isSidechain": True, "agentId": "A1", "uuid": "x1", "timestamp": at("00:10"),
                       "message": {"id": "mx1", "content": [{"type": "text", "text": "child thinking"},
                                                            {"type": "tool_use", "id": "c1", "name": "Bash", "input": {"command": "echo child"}}]}},
                      {"type": "user", "isSidechain": True, "message": {"content": [
                          {"type": "tool_result", "tool_use_id": "c1", "is_error": False, "content": "child"}]}},
                      dict(assistant("e4", [{"type": "text", "text": "streamed child"}]), isSidechain=True, agentId="A1", timestamp=at("00:15")),
                      dict(assistant("e2", []), timestamp=at("00:20")),
                      {"type": "user", "timestamp": at("05:00"), "message": {"content": "second prompt"}},
                      dict(assistant("e3", []), timestamp=at("05:05"))]
        record = claude.record_from(stream, transcript, False)
        shown = [(a["turn"], a["kind"], a.get("text") or a.get("command") or a.get("name"), a.get("agent")) for a in record["actions"]]
        self.assertEqual(shown, [(1, "other", "Task", None), (1, "message", "child thinking", "A1"),
                                 (1, "command", "echo child", "A1"), (1, "message", "streamed child", "t1"),
                                 (1, "message", "parent one", None), (2, "message", "parent two", None)])
        # with no time for the streamed events, the subagent's own actions still stay in their turn, at its end
        untimed = [[{k: v for k, v in e.items() if k != "uuid"} for e in turn] for turn in stream]
        record = claude.record_from(untimed, transcript, False)
        shown = [(a["turn"], a.get("text") or a.get("command") or a.get("name")) for a in record["actions"]]
        self.assertEqual(shown, [(1, "Task"), (1, "streamed child"), (1, "parent one"), (1, "child thinking"),
                                 (1, "echo child"), (2, "parent two")])

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
