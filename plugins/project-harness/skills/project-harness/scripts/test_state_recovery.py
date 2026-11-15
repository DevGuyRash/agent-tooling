#!/usr/bin/env python3
"""State recovery through the real CLI, with focused I/O failure controls."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('project_harness.py')
spec = importlib.util.spec_from_file_location('harness', SCRIPT)
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class StateRecovery(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        (self.repo / 'package.json').write_text('{"name":"fixture"}')
        self.state = self.repo / '.local/harness/state.json'
        self.state.parent.mkdir(parents=True)

    def cli(self, command='update'):
        result = subprocess.run([sys.executable, str(SCRIPT), command, str(self.repo), '--ci-mode', 'none'],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_invalid_shape_recovers_and_preserves_every_original(self):
        invalid = [[], None, 3, 'text', {'selected': None}, {'selected': []}, {'selected': 'text'}]
        old_backup = self.state.with_name('state.json.corrupt')
        old_backup.write_bytes(b'prior recovery evidence')
        (self.repo / 'justfile').write_text('# custom user task\n')
        for index, value in enumerate(invalid, 1):
            raw = json.dumps(value).encode()
            self.state.write_bytes(raw)
            result = self.cli()
            backup = self.state.with_name(f'state.json.corrupt.{index}')
            self.assertEqual(backup.read_bytes(), raw)
            self.assertTrue(any(backup.name in warning for warning in result['warnings']))
            self.assertIsInstance(json.loads(self.state.read_text())['selected'], dict)
            self.assertEqual((self.repo / 'justfile').read_text(), '# custom user task\n')
            self.assertEqual(old_backup.read_bytes(), b'prior recovery evidence')
        self.assertEqual(len(list(self.state.parent.glob('state.json.corrupt*'))), len(invalid) + 1)

    def test_invalid_json_and_utf8_recover_during_preview_without_target_writes(self):
        for raw in (b'{broken', b'\xff'):
            self.state.write_bytes(raw)
            result = self.cli('render')
            backup = self.state.parent / next(w.split()[-1] for w in result['warnings'] if 'was moved to' in w)
            self.assertEqual(backup.read_bytes(), raw)
            self.assertFalse((self.repo / 'justfile').exists())
            self.assertFalse((self.repo / '.gitignore').exists())
            self.assertFalse((self.repo / '.gitattributes').exists())

    def test_valid_legacy_state_preserves_selection_and_creation(self):
        for state in ({}, {'created_at': 'old', 'selected': {'architecture': 'general', 'ci_mode': 'none'}, 'future': {'opaque': True}}):
            self.state.write_text(json.dumps(state))
            self.cli()
            current = json.loads(self.state.read_text())
            if 'created_at' in state:
                self.assertEqual(current['created_at'], 'old')
                self.assertEqual(current['selected']['architecture'], 'general')
            self.assertEqual(list(self.state.parent.glob('state.json.corrupt*')), [])

    def test_read_error_does_not_quarantine_or_write_targets(self):
        self.state.write_bytes(b'{}')
        original = Path.read_text
        def denied(path, *args, **kwargs):
            if path == self.state:
                raise PermissionError('read denied')
            return original(path, *args, **kwargs)
        args = harness.build_parser().parse_args(['update', str(self.repo)])
        with patch.object(Path, 'read_text', denied), self.assertRaises(PermissionError):
            args.func(args)
        self.assertEqual(self.state.read_bytes(), b'{}')
        self.assertEqual(list(self.state.parent.iterdir()), [self.state])
        self.assertFalse((self.repo / 'justfile').exists())

    def test_failed_backup_move_keeps_state_and_existing_backups(self):
        self.state.write_bytes(b'[]')
        backup = self.state.with_name('state.json.corrupt')
        backup.write_bytes(b'previous')
        args = harness.build_parser().parse_args(['update', str(self.repo)])
        with patch.object(Path, 'replace', side_effect=PermissionError('move denied')), self.assertRaises(PermissionError):
            args.func(args)
        self.assertEqual(self.state.read_bytes(), b'[]')
        self.assertEqual(backup.read_bytes(), b'previous')
        self.assertFalse(self.state.with_name('state.json.corrupt.1').exists())
        self.assertFalse((self.repo / 'justfile').exists())


if __name__ == '__main__':
    unittest.main()
