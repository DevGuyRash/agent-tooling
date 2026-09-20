import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_workspaces.py"
MODULE_SPEC = importlib.util.spec_from_file_location("prepare_workspaces", SCRIPT)
HELPER = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(HELPER)


class WorkspacePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.host_temporary = Path(tempfile.gettempdir()).resolve()
        self.root = Path(self.temporary.name).resolve()
        self.sources = self.root / "sources"
        self.sources.mkdir()
        (self.sources / "task.md").write_text("Original assignment.\n", encoding="utf-8")
        package = self.sources / "package"
        (package / "references").mkdir(parents=True)
        (package / "SKILL.md").write_text("Read references/source.md.\n", encoding="utf-8")
        (package / "references/source.md").write_text("Authoritative source.\n", encoding="utf-8")
        self.context = self.root / ".local/context/experiment"
        self.context.mkdir(parents=True)
        self.system_temporary = self.root / "system-temporary"
        self.system_temporary.mkdir()
        temporary_location = mock.patch.object(HELPER.tempfile, "gettempdir", return_value=str(self.system_temporary))
        temporary_location.start()
        self.addCleanup(temporary_location.stop)
        self.spec_file = self.root / "batch.json"
        self.spec = {
            "inputs": {
                "task": {"source": "sources/task.md", "destination": "assignment.md"},
                "package": {"source": "sources/package", "destination": "package"},
            },
            "groups": [
                {"id": "a", "count": 2, "inputs": ["task", "package"], "outputs": ["response.md", "artifacts"]},
                {"id": "b", "count": 1, "inputs": ["task"], "outputs": ["notes.md"]},
            ],
        }

    def write_spec(self):
        self.spec_file.write_text(json.dumps(self.spec), encoding="utf-8")

    def prepare(self, name="batch-1"):
        self.write_spec()
        return HELPER.prepare_batch(self.context / name, self.spec_file)

    def cli(self, *extra, root=None):
        self.write_spec()
        return subprocess.run([sys.executable, str(SCRIPT), "--run-root", str(root or self.context / "cli"),
                               "--spec", str(self.spec_file), *extra], capture_output=True, text=True,
                              env={**os.environ, "TMPDIR": str(self.system_temporary)})

    def assert_rejected_without_root(self, spec=None):
        if spec is not None:
            self.spec = spec
        with self.assertRaises(HELPER.PreparationError):
            self.prepare()
        self.assertFalse((self.context / "batch-1").exists())

    def test_varied_groups_copy_only_selections_and_preserve_resources(self):
        result = self.prepare()
        self.assertEqual(result["preparation_status"], "ready")
        people = result["participants"]
        temporary_root = Path(result["temporary_root"])
        self.assertEqual(temporary_root.parent, self.system_temporary)
        self.assertFalse(HELPER.within(temporary_root, self.context))
        self.assertFalse((Path(result["run_root"]) / "participants").exists())
        self.assertEqual(len(people), 3)
        self.assertEqual(len({person["id"] for person in people}), 3)
        for person in people:
            self.assertTrue(HELPER.within(Path(person["workspace"]), temporary_root))
            inputs = Path(person["workspace"]) / "inputs"
            self.assertEqual(Path(person["inputs"]["task"]).read_text(), "Original assignment.\n")
            self.assertEqual({path.name for path in inputs.iterdir()},
                             {"assignment.md", "package"} if person["group"] == "a" else {"assignment.md"})
            if person["group"] == "a":
                self.assertEqual((inputs / "package/references/source.md").read_text(), "Authoritative source.\n")
            self.assertIsNone(person["host_agent_id"])
            self.assertTrue(person["prepared"])
            self.assertEqual(list(Path(person["output_root"]).iterdir()), [])
            self.assertTrue(all(not Path(path).exists() for path in person["expected_outputs"]))
            self.assertTrue(Path(person["retained_outputs"]).is_dir())
        Path(people[0]["inputs"]["task"]).write_text("A participant's local edit.\n")
        self.assertEqual(Path(people[1]["inputs"]["task"]).read_text(), "Original assignment.\n")
        self.assertEqual((self.sources / "task.md").read_text(), "Original assignment.\n")
        manifest = json.loads(Path(result["manifest"]).read_text())
        self.assertEqual(manifest["preparation_status"], "ready")
        self.assertTrue(manifest["temporary_root_created"])
        self.assertEqual(manifest["temporary_root"], result["temporary_root"])
        self.assertEqual(manifest["boundaries"]["host_enforced"], [])
        self.assertIn("no_access_to_sibling_workspaces_or_controller_archive",
                      manifest["boundaries"]["requires_agent_compliance"])

    def test_count_one_with_no_inputs_is_an_explicit_assignment(self):
        self.spec = {"inputs": {}, "groups": [{"id": "research", "count": 1, "inputs": [], "outputs": ["findings.md"]}]}
        result = self.prepare()
        self.assertEqual(result["participants"][0]["inputs"], {})

    def test_cli_outputs_one_json_line_and_optional_summary(self):
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(len(json.loads(result.stdout)["participants"]), 3)
        summary = self.cli("--summary-only", root=self.context / "summary")
        value = json.loads(summary.stdout)
        self.assertEqual(value["participant_count"], 3)
        self.assertNotIn("participants", value)
        self.assertEqual(len(json.loads(Path(value["manifest"]).read_text())["participants"]), 3)

    def test_default_system_temporary_location_and_controller_retention(self):
        self.write_spec()
        result = subprocess.run([sys.executable, str(SCRIPT), "--run-root", str(self.context / "native-temp"),
                                 "--spec", str(self.spec_file)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        batch = json.loads(result.stdout)
        temporary_root = Path(batch["temporary_root"])
        self.addCleanup(HELPER.shutil.rmtree, temporary_root, True)
        self.assertEqual(temporary_root.parent, self.host_temporary)
        participant = batch["participants"][0]
        response = Path(participant["expected_outputs"][0])
        response.write_text("Native smoke fixture; no agent execution.\n")
        artifacts = Path(participant["expected_outputs"][1])
        artifacts.mkdir()
        (artifacts / "data.bin").write_bytes(bytes([0, 1, 255]))
        retained = Path(participant["retained_outputs"])
        HELPER.shutil.copy2(response, retained / response.name)
        HELPER.shutil.copytree(artifacts, retained / artifacts.name)
        HELPER.shutil.rmtree(temporary_root)
        self.assertFalse(temporary_root.exists())
        self.assertEqual((retained / response.name).read_text(), "Native smoke fixture; no agent execution.\n")
        self.assertEqual((retained / artifacts.name / "data.bin").read_bytes(), bytes([0, 1, 255]))

    def test_completed_rerun_refuses_and_preserves_native_outputs(self):
        result = self.prepare()
        report = Path(result["participants"][0]["expected_outputs"][0])
        report.write_text("Native output, not a helper template.\n")
        manifest = Path(result["manifest"]).read_bytes()
        with self.assertRaisesRegex(HELPER.PreparationError, "already exists"):
            self.prepare()
        self.assertEqual(report.read_text(), "Native output, not a helper template.\n")
        self.assertEqual(Path(result["manifest"]).read_bytes(), manifest)
        next_batch = self.prepare("batch-2")
        self.assertNotEqual(result["run_root"], next_batch["run_root"])
        self.assertEqual(report.read_text(), "Native output, not a helper template.\n")

    def test_concurrent_distinct_runs_and_same_root_claim(self):
        self.write_spec()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda number: HELPER.prepare_batch(self.context / ("parallel-" + str(number)), self.spec_file), range(4)))
        workspaces = [person["workspace"] for result in results for person in result["participants"]]
        self.assertEqual(len(workspaces), len(set(workspaces)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
            tasks = [workers.submit(HELPER.prepare_batch, self.context / "shared", self.spec_file) for _ in range(2)]
        winners = [task.result() for task in tasks if task.exception() is None]
        failures = [task.exception() for task in tasks if task.exception() is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], HELPER.PreparationError)
        self.assertEqual(json.loads(Path(winners[0]["manifest"]).read_text())["preparation_status"], "ready")

    def test_missing_inputs_and_output_expectations_fail_before_claim(self):
        original = json.loads(json.dumps(self.spec))
        for change in ("missing-file", "undeclared", "missing-outputs", "empty-outputs"):
            with self.subTest(change=change):
                self.spec = json.loads(json.dumps(original))
                if change == "missing-file":
                    self.spec["inputs"]["task"]["source"] = "missing.md"
                elif change == "undeclared":
                    self.spec["groups"][0]["inputs"] = ["not-declared"]
                elif change == "missing-outputs":
                    del self.spec["groups"][0]["outputs"]
                else:
                    self.spec["groups"][0]["outputs"] = []
                self.assert_rejected_without_root()

    def test_invalid_counts_unknown_fields_and_duplicate_ids_fail(self):
        original = json.loads(json.dumps(self.spec))
        for value in (0, -1, True, 1.5, "2"):
            with self.subTest(count=value):
                self.spec = json.loads(json.dumps(original))
                self.spec["groups"][0]["count"] = value
                self.assert_rejected_without_root()
        self.spec = json.loads(json.dumps(original))
        self.spec["groups"][0]["role"] = "not part of this mechanical schema"
        self.assert_rejected_without_root()
        self.spec = json.loads(json.dumps(original))
        self.spec["groups"][1]["id"] = "a"
        self.assert_rejected_without_root()

    def test_unsafe_input_and_output_destinations_are_rejected(self):
        original = json.loads(json.dumps(self.spec))
        for value in ("../escape", "/absolute", "a/../../escape", "a\\b", "C:/escape", "a//b", "a/./b", "", "a\x00b"):
            for field in ("input", "output"):
                with self.subTest(value=value, field=field):
                    self.spec = json.loads(json.dumps(original))
                    if field == "input":
                        self.spec["inputs"]["task"]["destination"] = value
                    else:
                        self.spec["groups"][0]["outputs"] = [value]
                    self.assert_rejected_without_root()

    def test_overlapping_mounts_rejected_only_when_selected_together(self):
        self.spec["inputs"]["task"]["destination"] = "package/task.md"
        self.assert_rejected_without_root()
        self.spec["groups"][0]["inputs"] = ["package"]
        self.assertEqual(len(self.prepare()["participants"]), 3)

    def test_run_root_must_be_new_canonical_and_outside_inputs(self):
        self.write_spec()
        with self.assertRaises(HELPER.PreparationError):
            HELPER.prepare_batch("relative-root", self.spec_file)
        with self.assertRaises(HELPER.PreparationError):
            HELPER.prepare_batch(self.context / ".." / "escape", self.spec_file)
        with self.assertRaises(HELPER.PreparationError):
            HELPER.prepare_batch(self.sources / "package" / "new-run", self.spec_file)
        sentinel = self.context / "sentinel"
        sentinel.write_text("unchanged")
        with self.assertRaises(HELPER.PreparationError):
            HELPER.prepare_batch(sentinel, self.spec_file)
        self.assertEqual(sentinel.read_text(), "unchanged")

    @unittest.skipUnless(hasattr(os, "symlink"), "requires filesystem symlinks")
    def test_internal_and_explicitly_selected_cross_input_symlinks_work(self):
        link = self.sources / "package/current.md"
        link.symlink_to("references/source.md")
        result = self.prepare()
        copied = Path(result["participants"][0]["inputs"]["package"]) / "current.md"
        self.assertTrue(copied.is_symlink())
        self.assertEqual(copied.read_text(), "Authoritative source.\n")
        link.unlink()
        link.symlink_to("../task.md")
        self.spec["inputs"]["task"]["destination"] = "task.md"
        result = self.prepare("cross-input")
        copied = Path(result["participants"][0]["inputs"]["package"]) / "current.md"
        self.assertEqual(copied.read_text(), "Original assignment.\n")

    @unittest.skipUnless(hasattr(os, "symlink"), "requires filesystem symlinks")
    def test_symlink_escapes_absolute_links_and_missing_targets_fail(self):
        link = self.sources / "package/current.md"
        for target in ("missing.md", str(self.sources / "task.md"), "current.md"):
            with self.subTest(target=target):
                link.symlink_to(target)
                self.assert_rejected_without_root()
                link.unlink()
        alias = self.root / "context-alias"
        alias.symlink_to(self.context, target_is_directory=True)
        self.write_spec()
        with self.assertRaisesRegex(HELPER.PreparationError, "symlink component"):
            HELPER.prepare_batch(alias / "new-run", self.spec_file)
        alias = self.sources / "alias.md"
        alias.symlink_to("task.md")
        self.spec["inputs"]["task"]["source"] = "sources/alias.md"
        self.assert_rejected_without_root()

    @unittest.skipUnless(hasattr(os, "symlink"), "requires filesystem symlinks")
    def test_source_valid_link_missing_in_copied_layout_fails(self):
        link = self.sources / "package/current.md"
        link.symlink_to("../task.md")
        self.assertTrue(link.exists())
        with self.assertRaisesRegex(HELPER.PreparationError, "copied input symlink is missing"):
            self.prepare()
        manifest = json.loads((self.context / "batch-1/archive/manifest.json").read_text())
        self.assertEqual(manifest["preparation_status"], "failed")
        self.assertFalse(Path(manifest["temporary_root"]).exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "requires filesystem symlinks")
    def test_directory_link_is_resolved_before_parent_traversal(self):
        package = self.sources / "package"
        (package / "real/inside").mkdir(parents=True)
        (package / "real/note.md").write_text("intended resource\n")
        (package / "alias").symlink_to("real/inside", target_is_directory=True)
        (package / "indirect.md").symlink_to("alias/../note.md")
        result = self.prepare()
        copied = Path(result["participants"][0]["inputs"]["package"]) / "indirect.md"
        self.assertEqual(copied.read_text(), "intended resource\n")

    @unittest.skipUnless(hasattr(os, "symlink"), "requires filesystem symlinks")
    def test_copied_link_cannot_retarget_another_assigned_resource(self):
        (self.sources / "other.md").write_text("different resource\n")
        (self.sources / "package/current.md").symlink_to("../task.md")
        self.spec["inputs"]["other"] = {"source": "sources/other.md", "destination": "task.md"}
        self.spec["groups"][0]["inputs"].append("other")
        with self.assertRaisesRegex(HELPER.PreparationError, "retargeted resource"):
            self.prepare()

    @unittest.skipUnless(hasattr(os, "symlink"), "requires filesystem symlinks")
    def test_reviewer_archive_escape_fixture_and_preserved_layout_control(self):
        origin = self.root / "origin"
        source_root = origin / "a/b/c/sources"
        package = source_root / "deep/nest/pkg"
        shallow = source_root / "shallow"
        source_archive = origin / "a/archive"
        for directory in (package, shallow, source_archive):
            directory.mkdir(parents=True)
        (source_archive / "source-note.md").write_text("harmless source\n")
        (package / "alias").symlink_to("../../../shallow", target_is_directory=True)
        (package / "link").symlink_to("alias/../../../../archive", target_is_directory=True)
        self.assertEqual((package / "link").resolve(strict=True), source_archive)
        self.spec = {
            "inputs": {
                "package": {"source": str(package), "destination": "deep/nest/pkg"},
                "shallow": {"source": str(shallow), "destination": "shallow"},
                "archive": {"source": str(source_archive), "destination": "archive"},
            },
            "groups": [
                {"id": "assigned", "count": 1, "inputs": ["package", "shallow", "archive"], "outputs": ["response.md"]},
                {"id": "private-other-assignment", "count": 1, "inputs": [], "outputs": ["response.md"]},
            ],
        }
        # Reproduce the exact old destination geometry with a harmless controller file.
        graph_root = self.root / "exact-copied-graph"
        input_root = graph_root / "participants/p/inputs"
        input_root.mkdir(parents=True)
        controller_archive = graph_root / "archive"
        controller_archive.mkdir()
        (controller_archive / "manifest.json").write_text('{"group":"private-other-assignment"}')
        _, groups = HELPER.plan_batch(self.spec, self.root, self.context / "future")
        HELPER.copy_nodes(groups[0]["nodes"], input_root)
        self.assertEqual((input_root / "deep/nest/pkg/link").resolve(strict=True), controller_archive)
        with self.assertRaisesRegex(HELPER.PreparationError, "escapes the assigned input tree"):
            HELPER.check_copied_links(groups[0]["nodes"], input_root)
        # The public helper must also reject this assignment before publishing ready.
        with self.assertRaisesRegex(HELPER.PreparationError, "copied input symlink"):
            self.prepare()
        manifest = json.loads((self.context / "batch-1/archive/manifest.json").read_text())
        self.assertEqual(manifest["preparation_status"], "failed")
        self.assertFalse(Path(manifest["temporary_root"]).exists())
        # Preserving the original complete package layout makes both links valid.
        self.spec["inputs"] = {"origin": {"source": str(origin), "destination": "origin"}}
        self.spec["groups"][0]["inputs"] = ["origin"]
        result = self.prepare("preserved-layout")
        copied = Path(result["participants"][0]["inputs"]["origin"]) / "a/b/c/sources/deep/nest/pkg/link"
        self.assertEqual((copied / "source-note.md").read_text(), "harmless source\n")

    @unittest.skipUnless(hasattr(os, "symlink"), "requires filesystem symlinks")
    def test_reviewer_copied_cycle_fixture_and_complete_selection_control(self):
        origin = self.root / "cycle-origin"
        origin.mkdir()
        (origin / "real.txt").write_text("real source\n")
        for directory in ("a", "b", "p", "q"):
            (origin / directory).mkdir()
        for link, target in (("a/x", "../real.txt"), ("b/y", "../real.txt"),
                             ("p/x", "../b/y"), ("q/y", "../a/x")):
            (origin / link).symlink_to(target)
        self.assertEqual((origin / "p/x").read_text(), "real source\n")
        self.assertEqual((origin / "q/y").read_text(), "real source\n")
        self.spec = {
            "inputs": {"p": {"source": str(origin / "p"), "destination": "a"},
                       "q": {"source": str(origin / "q"), "destination": "b"}},
            "groups": [{"id": "assigned", "count": 1, "inputs": ["p", "q"], "outputs": ["response.md"]}],
        }
        with self.assertRaisesRegex(HELPER.PreparationError, "copied input symlink is missing, cyclic"):
            self.prepare()
        manifest = json.loads((self.context / "batch-1/archive/manifest.json").read_text())
        self.assertEqual(manifest["preparation_status"], "failed")
        self.assertFalse(Path(manifest["temporary_root"]).exists())
        self.spec["inputs"] = {name: {"source": str(origin / name), "destination": name}
                               for name in ("a", "b", "p", "q", "real.txt")}
        self.spec["inputs"]["real"] = self.spec["inputs"].pop("real.txt")
        self.spec["groups"][0]["inputs"] = list(self.spec["inputs"])
        result = self.prepare("complete-selection")
        copied = Path(result["participants"][0]["workspace"]) / "inputs"
        self.assertEqual((copied / "p/x").read_text(), "real source\n")
        self.assertEqual((copied / "q/y").read_text(), "real source\n")

    def test_copy_failure_cleans_only_owned_temporary_workspaces(self):
        sentinel = self.context / "unrelated.txt"
        sentinel.write_text("keep")
        with mock.patch.object(HELPER, "copy_nodes", side_effect=OSError("simulated copy failure")):
            with self.assertRaises(HELPER.PreparationError):
                self.prepare()
        run_root = self.context / "batch-1"
        manifest = json.loads((run_root / "archive/manifest.json").read_text())
        self.assertEqual(manifest["preparation_status"], "failed")
        self.assertTrue(manifest["partial_workspaces_removed"])
        self.assertFalse(Path(manifest["temporary_root"]).exists())
        self.assertEqual(sentinel.read_text(), "keep")
        with self.assertRaisesRegex(HELPER.PreparationError, "already exists"):
            self.prepare()
        self.assertEqual(self.prepare("corrected")["preparation_status"], "ready")

    def test_temporary_name_collision_preserves_existing_directory(self):
        claimed = self.system_temporary / "split-testing-claimed"
        claimed.mkdir()
        (claimed / "sentinel").write_text("unrelated")
        with mock.patch.object(HELPER.uuid, "uuid4", return_value=mock.Mock(hex="claimed")):
            with self.assertRaises(HELPER.PreparationError):
                self.prepare()
        self.assertEqual((claimed / "sentinel").read_text(), "unrelated")
        manifest = json.loads((self.context / "batch-1/archive/manifest.json").read_text())
        self.assertEqual(manifest["preparation_status"], "failed")
        self.assertFalse(manifest["temporary_root_created"])

    def test_cleanup_failure_retains_recoverable_location_and_failure_status(self):
        with mock.patch.object(HELPER, "copy_nodes", side_effect=OSError("simulated copy failure")):
            with mock.patch.object(HELPER.shutil, "rmtree", side_effect=PermissionError("simulated cleanup failure")):
                with self.assertRaises(HELPER.PreparationError):
                    self.prepare()
        manifest = json.loads((self.context / "batch-1/archive/manifest.json").read_text())
        self.assertEqual(manifest["preparation_status"], "failed")
        self.assertTrue(manifest["temporary_root_created"])
        self.assertFalse(manifest["partial_workspaces_removed"])
        self.assertEqual(manifest["cleanup_failure"], "PermissionError")
        self.assertTrue(Path(manifest["temporary_root"]).is_dir())

    def test_changed_input_fails_without_publishing_a_ready_batch(self):
        original = HELPER.copy_nodes

        def mutate_then_copy(nodes, destination):
            (self.sources / "task.md").write_text("changed during preparation\n")
            original(nodes, destination)

        with mock.patch.object(HELPER, "copy_nodes", side_effect=mutate_then_copy):
            with self.assertRaisesRegex(HELPER.PreparationError, "input changed"):
                self.prepare()
        manifest = json.loads((self.context / "batch-1/archive/manifest.json").read_text())
        self.assertEqual(manifest["preparation_status"], "failed")

    @unittest.skipUnless(os.name == "posix", "tests POSIX signal delivery")
    def test_sigterm_and_sigkill_leave_distinguishable_incomplete_batches(self):
        self.write_spec()
        harness = """
import os, runpy, shutil, signal, sys
selected_signal = int(sys.argv[1])
def stop_during_copy(reader, writer, *args):
    writer.write(reader.read(1))
    writer.flush()
    os.kill(os.getpid(), selected_signal)
shutil.copyfileobj = stop_during_copy
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name='__main__')
"""
        for selected_signal in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=selected_signal):
                run_root = self.context / ("signal-" + str(selected_signal))
                result = subprocess.run([sys.executable, "-c", harness, str(selected_signal), str(SCRIPT),
                                         "--run-root", str(run_root), "--spec", str(self.spec_file)],
                                        capture_output=True, text=True,
                                        env={**os.environ, "TMPDIR": str(self.system_temporary)})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)
                manifest = json.loads((run_root / "archive/manifest.json").read_text())
                self.assertEqual(manifest["preparation_status"], "interrupted" if selected_signal == signal.SIGTERM else "preparing")
                self.assertEqual(Path(manifest["temporary_root"]).exists(), selected_signal == signal.SIGKILL)
                with self.assertRaisesRegex(HELPER.PreparationError, "already exists"):
                    HELPER.prepare_batch(run_root, self.spec_file)

    def test_interruption_after_commit_preserves_prepared_inputs(self):
        original = HELPER.write_manifest

        def commit_then_interrupt(path, manifest):
            original(path, manifest)
            if manifest["preparation_status"] == "ready":
                raise KeyboardInterrupt()

        with mock.patch.object(HELPER, "write_manifest", side_effect=commit_then_interrupt):
            with self.assertRaisesRegex(HELPER.PreparationError, "batch is ready"):
                self.prepare()
        manifest = json.loads((self.context / "batch-1/archive/manifest.json").read_text())
        self.assertEqual(manifest["preparation_status"], "ready")
        self.assertEqual(Path(manifest["participants"][0]["inputs"]["task"]).read_text(), "Original assignment.\n")

    def test_cli_errors_are_concise_and_do_not_emit_success_json(self):
        self.spec["groups"][0]["outputs"] = []
        result = self.cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.splitlines()), 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_json_keys_are_rejected(self):
        self.spec_file.write_text('{"inputs":{},"inputs":{},"groups":[]}', encoding="utf-8")
        with self.assertRaisesRegex(HELPER.PreparationError, "repeats a JSON field"):
            HELPER.prepare_batch(self.context / "duplicates", self.spec_file)
        self.assertFalse((self.context / "duplicates").exists())


if __name__ == "__main__":
    unittest.main()
