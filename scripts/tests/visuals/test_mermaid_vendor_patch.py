"""Pinned-byte and output-preservation checks for the manual renderer patches."""
from pathlib import Path
import hashlib
import importlib.util
import tempfile
import subprocess
import unittest

REPOSITORY = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("mermaid_vendor_patch", REPOSITORY / "scripts/patch_mermaid_vendor.py")
assert SPEC and SPEC.loader
PATCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCHER)
VENDOR = REPOSITORY / "plugins/agentic-design-and-evaluation/skills/split-testing/assets/visuals/vendor/mermaid/mermaid.min.js"


class MermaidVendorPatchTests(unittest.TestCase):
    def test_diamond_callback_survives_block_graph_copy(self):
        subprocess.run(["node", str(REPOSITORY / "scripts/tests/visuals/diamond_intersection.cjs")], check=True)

    def test_venn_label_regions_preserve_membership(self):
        subprocess.run(["node", str(REPOSITORY / "scripts/tests/visuals/venn_geometry.cjs")], check=True)

    @classmethod
    def setUpClass(cls):
        cls.installed = VENDOR.read_bytes()
        digest = hashlib.sha256(cls.installed).hexdigest()
        if digest == PATCHER.PATCHED_SHA256:
            cls.upstream = PATCHER.restore_upstream(cls.installed)
        elif digest == PATCHER.UPSTREAM_SHA256:
            cls.upstream = cls.installed
        else:
            raise AssertionError("installed Mermaid is neither the reviewed upstream nor patched artifact")

    def test_patches_are_exactly_the_reviewed_reversible_changes(self):
        self.assertEqual(hashlib.sha256(self.upstream).hexdigest(), PATCHER.UPSTREAM_SHA256)
        candidate = PATCHER.patch(self.upstream)
        self.assertEqual(hashlib.sha256(candidate).hexdigest(), PATCHER.PATCHED_SHA256)
        for name, before, after in PATCHER.replacements():
            self.assertEqual(candidate.count(after), 1, name)
        self.assertEqual(PATCHER.restore_upstream(candidate), self.upstream)

    def test_unknown_or_already_patched_input_is_rejected(self):
        for data in (self.upstream + b"\n", PATCHER.patch(self.upstream)):
            with self.assertRaises(ValueError):
                PATCHER.patch(data)

    def test_existing_output_and_input_are_preserved_without_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.js"
            output = Path(directory) / "output.js"
            source.write_bytes(self.upstream)
            output.write_bytes(b"retained unrelated output")
            self.assertEqual(PATCHER.main(["--input", str(source), "--output", str(output)]), 2)
            self.assertEqual(output.read_bytes(), b"retained unrelated output")
            self.assertEqual(source.read_bytes(), self.upstream)
            self.assertEqual(PATCHER.main(["--input", str(source), "--output", str(source), "--replace"]), 2)
            self.assertEqual(source.read_bytes(), self.upstream)

    def test_check_and_identical_rerun_preserve_generated_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.js"
            output = Path(directory) / "output.js"
            source.write_bytes(self.upstream)
            args = ["--input", str(source), "--output", str(output)]
            self.assertEqual(PATCHER.main(args), 0)
            before = output.stat().st_mtime_ns
            self.assertEqual(PATCHER.main(args + ["--check"]), 0)
            self.assertEqual(PATCHER.main(args), 0)
            self.assertEqual(output.stat().st_mtime_ns, before)


if __name__ == "__main__":
    unittest.main()
