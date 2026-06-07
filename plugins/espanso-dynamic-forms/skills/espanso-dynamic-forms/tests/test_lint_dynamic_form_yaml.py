from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lint_dynamic_form_yaml.py"
SPEC = importlib.util.spec_from_file_location("lint_dynamic_form_yaml", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"failed to load script module from {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LintDynamicFormYamlTests(unittest.TestCase):
    def test_lint_text_accepts_real_contract_args(self):
        text = """
matches:
  - trigger: ":x"
    vars:
      - name: layout_generator
        type: script
        params:
          args:
            - ESPANSO_FORM_OPERATION=layout
            - ESPANSO_FORM_PROVIDER=demo
            - ESPANSO_FORM_FIELD_input_mode=text
"""
        errors, warnings = MODULE.lint_text(text)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_lint_text_rejects_comment_only_required_keys(self):
        text = """
# - ESPANSO_FORM_OPERATION=layout
# - ESPANSO_FORM_PROVIDER=demo
matches:
  - trigger: ":x"
"""
        errors, warnings = MODULE.lint_text(text)
        self.assertTrue(errors)
        self.assertIn("ESPANSO_FORM_OPERATION=", errors[0])
        self.assertIn("ESPANSO_FORM_PROVIDER=", errors[0])
        self.assertIn("no ESPANSO_FORM_FIELD_<name> keys found", warnings)

    def test_lint_text_accepts_quoted_contract_args(self):
        text = """
matches:
  - trigger: ":x"
    vars:
      - name: layout_generator
        type: script
        params:
          args:
            - "ESPANSO_FORM_OPERATION=layout"
            - 'ESPANSO_FORM_PROVIDER=demo'
            - "ESPANSO_FORM_FIELD_input_mode=text"
"""
        errors, warnings = MODULE.lint_text(text)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_lint_text_rejects_missing_required_key_in_one_of_multiple_blocks(self):
        text = """
matches:
  - trigger: ":ok"
    vars:
      - name: layout_generator
        type: script
        params:
          args:
            - ESPANSO_FORM_OPERATION=layout
            - ESPANSO_FORM_PROVIDER=demo
            - ESPANSO_FORM_FIELD_input_mode=text

  - trigger: ":bad"
    vars:
      - name: layout_generator
        type: script
        params:
          args:
            - ESPANSO_FORM_OPERATION=layout
            - ESPANSO_FORM_FIELD_input_mode=text
"""
        errors, warnings = MODULE.lint_text(text)
        self.assertTrue(errors)
        self.assertIn("layout_generator args block 2", errors[0])
        self.assertIn("ESPANSO_FORM_PROVIDER=", errors[0])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
