"""Codex evidence reaches the real trial consumer without turning gaps into absence."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_launchers import codex
from test_invocation import Launched, LauncherCase

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "coverage_trial", ROOT / "plugins/agentic-design-and-evaluation/skills/split-testing/scripts/trial.py")
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)
SKILL = "---\nname: helper\ndescription: A test helper.\n---\nInstructions."


def rollout(agent="T", items=(), complete=True):
    records = [{"type": "session_meta", "payload": {"id": agent}},
               {"type": "event_msg", "payload": {"type": "task_started"}}]
    records += [{"type": "event_msg", "payload": {"type": "item_completed", "item": item}} for item in items]
    if complete:
        records.append({"type": "event_msg", "payload": {"type": "task_complete"}})
    return records


class CodexCoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="codex-coverage-")
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)
        self.skill = self.job / "harness/home/skills/helper/SKILL.md"
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text(SKILL)

    def record(self, item=None, *, child=False, completed=True, rollouts=None, finished=True):
        events = [{"type": "thread.started", "thread_id": "T"}]
        sources = [rollout()]
        if child:
            events.append({"type": "item.completed", "item": {"id": "spawn", "type": "collab_tool_call",
                           "tool": "spawn_agent", "receiver_thread_ids": ["S"], "status": "completed"}})
            sources.append(rollout("S", [item] if completed else [], complete=completed))
            if not completed:
                sources[-1].append({"type": "response_item", "payload": {"type": "function_call",
                    "call_id": "pending", "name": "exec_command", "arguments": '{"cmd": "cat SKILL.md"}'}})
        elif item is not None:
            events.append({"type": "item.completed" if completed else "item.started", "item": item})
        if finished:
            events.append({"type": "turn.completed", "usage": {}})
        return codex.record_from([events], sources if rollouts is None else rollouts, False, str(self.job / "work"))

    def command(self, child=False, **fields):
        return {"id": "c", "type": "CommandExecution" if child else "command_execution",
                "command": "cat SKILL.md", "exit_code": 0, "status": "completed", **fields}

    def run_record(self, record):
        self.assertIsNone(trial._record_problem(record))
        return trial.Run(self.job, "ok", record=record)

    def assert_unknown(self, record):
        run = self.run_record(record)
        with self.assertRaises(trial.RecordUnavailable):
            run.skill_loaded("helper")
        with self.assertRaises(trial.RecordUnavailable):
            run.exposed(self.skill)

    def test_missing_null_and_nontext_command_output_are_not_empty_or_absence(self):
        for child in (False, True):
            for fields in ({}, {"aggregated_output": None}, {"aggregated_output": []}):
                with self.subTest(child=child, fields=fields):
                    record = self.record(self.command(child, **fields), child=child)
                    action = next(a for a in record["actions"] if a["kind"] == "command")
                    self.assertNotIn("output", action)
                    self.assertNotIn("command", record["covers"])
                    self.assert_unknown(record)

    def test_captured_empty_output_is_known_and_does_not_fall_back_to_stdout(self):
        for child in (False, True):
            with self.subTest(child=child):
                record = self.record(self.command(child, aggregated_output="", stdout=SKILL), child=child)
                action = next(a for a in record["actions"] if a["kind"] == "command")
                self.assertEqual(action["output"], "")
                self.assertIn("command", record["covers"])
        run = self.run_record(self.record(self.command(aggregated_output="")))
        self.assertFalse(run.skill_loaded("helper"))
        # Resource exposure is stricter than name-based skill selection: commands cannot prove a read or its absence.
        with self.assertRaises(trial.RecordUnavailable):
            run.exposed(self.skill)

    def test_incomplete_outcomes_do_not_claim_command_coverage(self):
        for child in (False, True):
            for fields, completed in (({"aggregated_output": "", "exit_code": None}, True),
                                      ({"aggregated_output": "", "status": "in_progress"}, True),
                                      ({"aggregated_output": ""}, False)):
                with self.subTest(child=child, fields=fields, completed=completed):
                    record = self.record(self.command(child, **fields), child=child, completed=completed)
                    self.assertNotIn("command", record["covers"])
                    self.assert_unknown(record)

    def test_truncated_output_is_partial_evidence_not_complete_coverage(self):
        for child in (False, True):
            for fields in ({"aggregated_output": "partial", "output_truncated": True},
                           {"aggregated_output": "Warning: truncated output (original token count: 9000)\npartial"},
                           {"aggregated_output": "...120 tokens truncated..."}):
                with self.subTest(child=child, fields=fields):
                    record = self.record(self.command(child, **fields), child=child)
                    self.assertNotIn("command", record["covers"])
                    self.assert_unknown(record)

    def test_positive_content_and_injected_loads_survive_incomplete_coverage(self):
        for child in (False, True):
            record = self.record(self.command(child, aggregated_output=SKILL, output_truncated=True), child=child)
            run = self.run_record(record)
            self.assertTrue(run.skill_loaded("helper"))
            with self.assertRaises(trial.RecordUnavailable):
                run.exposed(self.skill)
        source = rollout()
        source.insert(2, {"type": "response_item", "payload": {"type": "message", "role": "user",
                           "content": [{"text": "<skill><name>helper</name></skill>"}]}})
        run = self.run_record(self.record(self.command(), rollouts=[source]))
        self.assertTrue(run.skill_loaded("helper"))
        with self.assertRaises(trial.RecordUnavailable):
            run.exposed(self.skill)
        with self.assertRaises(trial.RecordUnavailable):
            run.skill_loaded("unseen")

    def test_injected_skill_content_reaches_the_resource_exposure_consumer(self):
        for child in (False, True):
            source = rollout("S" if child else "T")
            source.insert(2, {"type": "response_item", "payload": {"type": "message", "role": "user",
                "content": [{"text": "<skill><name>helper</name>\n" + SKILL + "\n</skill>"}]}})
            record = self.record(rollouts=[rollout(), source] if child else [source])
            run = self.run_record(record)
            self.assertTrue(run.skill_loaded("helper"))
            self.assertTrue(run.exposed(self.skill))

    def test_partial_stdout_survives_an_unavailable_aggregate(self):
        for child in (False, True):
            record = self.record(self.command(child, aggregated_output=None, stdout=SKILL), child=child)
            self.assertTrue(self.run_record(record).skill_loaded("helper"))
            self.assertNotIn("command", record["covers"])

    def test_message_availability_is_the_same_for_main_and_children(self):
        for child, kind in ((False, "agent_message"), (True, "AgentMessage")):
            record = self.record({"id": "m", "type": kind}, child=child)
            self.assertNotIn("message", record["covers"])
            record = self.record({"id": "m", "type": kind, "text": ""}, child=child)
            self.assertIn("message", record["covers"])

    def test_missing_action_subjects_do_not_poison_serialized_positive_evidence(self):
        source = rollout()
        source.insert(2, {"type": "response_item", "payload": {"type": "message", "role": "user",
            "content": [{"text": "<skill><name>helper</name>\n" + SKILL + "\n</skill>"}]}})
        for child in (False, True):
            for item in ({"id": "m", "type": "AgentMessage" if child else "agent_message"},
                         self.command(child, command=None, aggregated_output=SKILL)):
                with self.subTest(child=child, item=item):
                    sources = [source, rollout("S", [item])] if child else [source]
                    record = self.record(item, child=child, rollouts=sources)
                    path = self.job / "record.json"
                    path.write_text(json.dumps(record))
                    saved, problem = trial._read_record(path)
                    self.assertIsNone(problem)
                    run = self.run_record(saved)
                    self.assertTrue(run.skill_loaded("helper"))
                    self.assertTrue(run.exposed(self.skill))
                    if item.get("command") is None and "command" in item:
                        self.assertNotIn("command", saved["covers"])
                        self.assertTrue(any(a.get("output") == SKILL for a in saved["actions"]))

    def test_opaque_tools_do_not_claim_complete_other_actions_or_success(self):
        for child, kind in ((False, "mcp_tool_call"), (True, "McpToolCall")):
            record = self.record({"id": "opaque", "type": kind, "tool": "read_something"}, child=child)
            self.assertNotIn("other", record["covers"])
            action = next(a for a in record["actions"] if a.get("name") == "read_something")
            self.assertIsNone(action["ok"])
            self.assert_unknown(record)

    def test_opaque_output_is_still_positive_evidence(self):
        for child, kind in ((False, "mcp_tool_call"), (True, "McpToolCall")):
            record = self.record({"id": "opaque", "type": kind, "output": SKILL}, child=child)
            self.assertTrue(self.run_record(record).skill_loaded("helper"))
            self.assertNotIn("other", record["covers"])

    def test_missing_or_in_progress_edit_status_is_unknown(self):
        for child, kind in ((False, "file_change"), (True, "FileChange")):
            for status in (None, "in_progress", "unrecognized"):
                record = self.record({"id": "edit", "type": kind, "changes": [{"path": "a.py"}],
                                      "status": status}, child=child)
                self.assertNotIn("edit", record["covers"])
                self.assertIsNone(next(a for a in record["actions"] if a["kind"] == "edit")["ok"])

    def test_pending_generic_child_call_is_retained_as_partial_evidence(self):
        source = rollout("S")
        source.insert(2, {"type": "response_item", "payload": {"type": "function_call", "call_id": "u",
                                                               "name": "read_document", "arguments": "{}"}})
        record = self.record(rollouts=[rollout(), source])
        self.assertNotIn("other", record["covers"])
        self.assertTrue(any(a.get("name") == "read_document" and a.get("agent") == "S" for a in record["actions"]))
        self.assert_unknown(record)

    def test_missing_grandchild_invalidates_global_coverage(self):
        source = rollout("S", [{"id": "spawn", "type": "CollabAgentToolCall", "tool": "spawn_agent",
                                "receiver_thread_ids": ["G"], "status": "completed"}])
        record = self.record(rollouts=[rollout(), source])
        self.assertEqual(record["covers"], [])
        self.assert_unknown(record)

    def test_missing_main_or_spawned_rollout_cannot_prove_absence(self):
        record = self.record(self.command(aggregated_output=""), rollouts=[])
        self.assertNotIn("load", record["covers"])
        self.assert_unknown(record)
        record = self.record(self.command(True, aggregated_output=""), child=True, rollouts=[rollout()])
        self.assertEqual(record["covers"], [])
        self.assert_unknown(record)

    def test_unfinished_stream_or_rollout_cannot_prove_absence(self):
        self.assert_unknown(self.record(self.command(aggregated_output=""), finished=False))
        self.assert_unknown(self.record(self.command(aggregated_output=""), rollouts=[rollout(complete=False)]))

    def test_main_raw_tool_output_is_positive_evidence_not_hidden_absence(self):
        source = rollout()
        source[2:2] = [
            {"type": "response_item", "payload": {"type": "function_call", "call_id": "r",
                "name": "read_file", "arguments": "{}"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "r", "output": SKILL}}]
        record = self.record(rollouts=[source])
        self.assertNotIn("other", record["covers"])
        run = self.run_record(record)
        self.assertTrue(run.skill_loaded("helper"))
        with self.assertRaises(trial.RecordUnavailable):
            run.skill_loaded("unseen")

    def test_main_unrepresented_command_cannot_prove_absence(self):
        source = rollout()
        source.insert(2, {"type": "response_item", "payload": {"type": "function_call", "call_id": "r",
                            "name": "exec_command", "arguments": '{"cmd": "cat SKILL.md"}'}})
        record = self.record(rollouts=[source])
        self.assertNotIn("command", record["covers"])
        self.assert_unknown(record)

    def test_unrepresented_command_outputs_survive_in_both_native_formats(self):
        for child in (False, True):
            for legacy in (False, True):
                with self.subTest(child=child, legacy=legacy):
                    source = rollout("S" if child else "T")
                    if legacy:
                        records = [{"type": "event_msg", "payload": {"type": "exec_command_begin", "call_id": "r",
                                    "command": ["cat", "SKILL.md"]}},
                                   {"type": "event_msg", "payload": {"type": "exec_command_end", "call_id": "r",
                                    "command": ["cat", "SKILL.md"], "exit_code": 0, "aggregated_output": SKILL}}]
                    else:
                        records = [{"type": "response_item", "payload": {"type": "function_call", "call_id": "r",
                                    "name": "exec_command", "arguments": '{"cmd": "cat SKILL.md"}'}},
                                   {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "r",
                                    "output": SKILL}}]
                    source[2:2] = records
                    record = self.record(rollouts=[rollout(), source] if child else [source])
                    self.assertTrue(self.run_record(record).skill_loaded("helper"))
                    if not child or not legacy:
                        self.assertNotIn("command", record["covers"])

    def test_rollout_must_cover_every_event_turn(self):
        events = [[{"type": "thread.started", "thread_id": "T"}, {"type": "turn.completed"}],
                  [{"type": "turn.completed"}]]
        record = codex.record_from(events, [rollout()], False, str(self.job / "work"))
        self.assertNotIn("load", record["covers"])
        self.assert_unknown(record)


class CodexConsumerInvocationTest(LauncherCase):
    name = "codex"

    def test_real_launcher_serializes_evidence_for_the_real_consumer(self):
        module = self.launcher()
        with mock.patch.dict(os.environ, {**self.env, "TRIAL_TURN": "0"}):
            self.assertEqual(module.main(), 0)
        sessions = module.CODEX / "sessions"
        sessions.mkdir()
        native = sessions / "rollout-main.jsonl"
        native.write_text("\n".join(json.dumps(r) for r in rollout()))
        for fields, expected in (({}, None), ({"aggregated_output": ""}, False),
                                 ({"aggregated_output": SKILL, "output_truncated": True}, True)):
            with self.subTest(fields=fields):
                events = [{"type": "thread.started", "thread_id": "T"},
                          {"type": "item.completed", "item": {"id": "c", "type": "command_execution",
                              "command": "cat SKILL.md", "exit_code": 0, "status": "completed", **fields}},
                          {"type": "turn.completed", "usage": {}}]
                with mock.patch("sys.stdout", mock.Mock()):
                    self.assertEqual(self.turn(module, 1, Launched([events])), 0)
                record, problem = trial._read_record(self.tmp / "record.json")
                self.assertIsNone(problem)
                run = trial.Run(self.tmp, "ok", record=record)
                if expected is None:
                    with self.assertRaises(trial.RecordUnavailable):
                        run.skill_loaded("helper")
                else:
                    self.assertIs(run.skill_loaded("helper"), expected)

    def test_corrupt_or_missing_native_records_keep_positives_but_no_coverage(self):
        module = self.launcher()
        module.STATE.mkdir()
        events = [{"type": "thread.started", "thread_id": "T"},
                  {"type": "item.completed", "item": {"id": "c", "type": "command_execution",
                      "command": "cat SKILL.md", "exit_code": 0, "aggregated_output": SKILL}},
                  {"type": "turn.completed", "usage": {}}]
        path = module.STATE / "events-1.jsonl"
        text = "\n".join(json.dumps(e) for e in events)
        for tail in ('\n{"type":', '\nnull', '\n\ufffd'):
            with self.subTest(tail=tail), mock.patch.dict(os.environ, self.env):
                path.write_text(text + tail)
                module.write_record(1)
                record = json.loads((self.tmp / "record.json").read_text())
                self.assertEqual(record["covers"], [])
                self.assertGreater(len(record["limits"]), 1)  # no-rollout note does not erase the gap
                self.assertTrue(trial.Run(self.tmp, "ok", record=record).skill_loaded("helper"))
        path.write_text(text)
        with mock.patch.dict(os.environ, self.env):
            module.write_record(2)
        record = json.loads((self.tmp / "record.json").read_text())
        self.assertEqual(record["covers"], [])
        self.assertEqual(len(record["turns"]), 2)


if __name__ == "__main__":
    unittest.main()
