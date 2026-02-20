from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scaffold_dynamic_form.py"
SPEC = importlib.util.spec_from_file_location("scaffold_dynamic_form", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"failed to load script module from {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NormalizeFieldsTests(unittest.TestCase):
    def test_allows_rust_safe_field_names_for_provider_scaffold(self):
        fields = MODULE.normalize_fields(
            "secret,input_mode,_private", rust_identifiers=True
        )
        self.assertEqual(fields, ["secret", "input_mode", "_private"])

    def test_rejects_leading_digit_for_provider_scaffold(self):
        with self.assertRaisesRegex(ValueError, "provider scaffold requires a Rust-safe identifier"):
            MODULE.normalize_fields("1bad", rust_identifiers=True)

    def test_rejects_rust_keyword_for_provider_scaffold(self):
        with self.assertRaisesRegex(ValueError, "provider scaffold requires a Rust-safe identifier"):
            MODULE.normalize_fields("match", rust_identifiers=True)


if __name__ == "__main__":
    unittest.main()
