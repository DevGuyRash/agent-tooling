"""Fresh contributor setup and actual Git-hook behavior in private repositories."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from scripts.tests import test_artifacts as fixtures

ROOT = Path(__file__).resolve().parents[2]


class ContributorBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ArtifactTasksTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        scripts = self.root / 'scripts'
        scripts.mkdir()
        shutil.copy2(ROOT / 'scripts/artifacts.py', scripts / 'artifacts.py')
        shutil.copytree(ROOT / 'scripts/artifact_sync', scripts / 'artifact_sync', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT / 'githooks', self.root / 'githooks')
        self.fixture.staged_fixture()
        self.cli = scripts / 'artifacts.py'

    def call(self, *args, root=None, env=None):
        result = subprocess.run([sys.executable, '-B', str(self.cli), '--repo', str(root or self.root), *args],
                                cwd=self.fixture.temp.name, env=env, capture_output=True, text=True, timeout=30)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def test_fresh_clone_bootstraps_idempotently_without_rebuilding_or_staging(self):
        clone = Path(self.fixture.temp.name) / 'fresh clone'
        self.fixture.git('clone', '-q', '--local', str(self.root), str(clone))
        index = (clone / '.git/index').read_bytes()
        receipt = (clone / 'packaging/receipts/upper.json').read_bytes()
        result = self.call('bootstrap', root=clone)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['hooks']['status'], 'enabled')
        config = (clone / '.git/config').read_bytes()
        again = self.call('bootstrap', root=clone)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(json.loads(again.stdout)['hooks']['status'], 'already-enabled')
        self.assertEqual((clone / '.git/config').read_bytes(), config)
        self.assertEqual((clone / '.git/index').read_bytes(), index)
        self.assertEqual((clone / 'packaging/receipts/upper.json').read_bytes(), receipt)
        self.assertEqual((clone / 'plugins/a/value.txt').read_text(), 'ALPHA\n')
        self.assertFalse((clone / 'context').exists(), 'setup must not execute a producer')

    def test_bootstrap_alone_enables_generation_on_next_commit(self):
        result = self.call('bootstrap')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.fixture.write('seed.txt', 'from contributor\n')
        self.fixture.git('add', 'seed.txt')
        self.fixture.git('commit', '-qm', 'first contributor change')
        self.assertEqual(self.fixture.git('show', 'HEAD:plugins/a/value.txt').stdout, 'FROM CONTRIBUTOR\n')
        self.assertEqual(self.fixture.git('diff', '--cached', '--name-only').stdout, '')

    def test_existing_hook_selection_is_preserved_without_explicit_replacement(self):
        self.fixture.git('config', '--local', 'core.hooksPath', 'custom-hooks')
        custom = self.fixture.write('custom-hooks/pre-commit', '#!/bin/sh\nexit 0\n')
        custom.chmod(0o755)
        config = (self.root / '.git/config').read_bytes()
        refused = self.call('bootstrap')
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('--replace-hooks', refused.stderr)
        self.assertEqual((self.root / '.git/config').read_bytes(), config)
        replacement = self.call('bootstrap', '--replace-hooks')
        self.assertEqual(replacement.returncode, 0, replacement.stderr)
        self.assertEqual(self.fixture.git('config', '--local', '--get', 'core.hooksPath').stdout.strip(), 'githooks')
        self.assertEqual(custom.read_text(), '#!/bin/sh\nexit 0\n')

    def test_native_hooks_and_explicitly_empty_selection_are_preserved(self):
        hook = self.fixture.write('.git/hooks/pre-commit', '#!/bin/sh\nexit 0\n')
        hook.chmod(0o755)
        result = self.call('hooks-install')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('existing native Git hooks', result.stderr)
        self.assertEqual(hook.read_text(), '#!/bin/sh\nexit 0\n')
        self.fixture.git('config', 'core.hooksPath', '')
        result = self.call('bootstrap')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('custom core.hooksPath', result.stderr)
        self.assertEqual(self.fixture.git('config', '--get', 'core.hooksPath').stdout, '\n')

    def test_missing_or_symlinked_maintained_hook_does_not_change_configuration(self):
        hook = self.root / 'githooks/pre-push'
        hook.unlink()
        before = (self.root / '.git/config').read_bytes()
        result = self.call('bootstrap')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / '.git/config').read_bytes(), before)
        external = Path(self.fixture.temp.name) / 'outside'
        external.write_text('#!/usr/bin/env sh\nexit 0\n')
        external.chmod(0o644)
        hook.symlink_to(external)
        self.assertNotEqual(self.call('bootstrap').returncode, 0)
        self.assertEqual(external.stat().st_mode & 0o777, 0o644)
        self.assertEqual((self.root / '.git/config').read_bytes(), before)

    def test_artifact_drift_is_reported_without_overwriting_it(self):
        self.fixture.write('plugins/a/value.txt', 'manual work')
        index = (self.root / '.git/index').read_bytes()
        result = self.call('bootstrap')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['artifacts']['status'], 'needs-attention')
        self.assertEqual((self.root / 'plugins/a/value.txt').read_text(), 'manual work')
        self.assertEqual((self.root / '.git/index').read_bytes(), index)
        self.assertEqual(self.fixture.git('config', '--get', 'core.hooksPath').stdout.strip(), 'githooks')

    def test_future_runtime_is_discovered_without_a_language_branch(self):
        tool_dir = Path(self.fixture.temp.name) / 'tools'
        tool_dir.mkdir()
        compiler = tool_dir / 'unfamiliar-future-runtime'
        compiler.symlink_to(sys.executable)
        env = {**os.environ, 'PATH': str(tool_dir) + os.pathsep + os.environ['PATH']}
        manifest = self.root / 'packaging/artifacts.toml'
        manifest.write_text(manifest.read_text().replace('"{python}", "build.py"', '"unfamiliar-future-runtime", "build.py"'))
        self.fixture.call(env=env)
        compiler.unlink()
        result = self.call('bootstrap')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['missing_build_tools'], [{'tool': 'unfamiliar-future-runtime', 'tasks': ['upper']}])
        strict = self.call('bootstrap', '--require-tools')
        self.assertEqual(strict.returncode, 2)
        self.assertEqual(json.loads(strict.stdout)['artifacts']['status'], 'current')

    def test_relative_command_and_task_specific_path_follow_the_execution_directory(self):
        builder = self.root / 'build.py'
        builder.write_text('#!/usr/bin/env python3\n' + builder.read_text())
        builder.chmod(0o755)
        manifest = self.root / 'packaging/artifacts.toml'
        manifest.write_text(manifest.read_text().replace('"{python}", "build.py"', '"./build.py"'))
        self.fixture.call()
        result = self.call('bootstrap', '--require-tools')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['missing_build_tools'], [])

    def test_selection_and_dependencies_come_from_the_manifest(self):
        self.fixture.write_manifest('''
[tasks.copy]
inputs=["seed.txt"]
[[tasks.copy.outputs]]
source="seed.txt"
destinations=["copied.txt"]
[tasks.manual]
automatic=false
inputs=["seed.txt"]
command=["never-execute-this-program"]
[[tasks.manual.outputs]]
source="seed.txt"
destinations=["external.txt"]
''')
        self.fixture.call()
        result = self.call('bootstrap', '--task', 'copy', '--require-tools')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['artifacts']['tasks'], ['copy'])
        self.assertFalse((self.root / 'external.txt').exists())
        self.assertNotEqual(self.call('bootstrap', '--task', 'unknown').returncode, 0)

    def test_worktree_configuration_does_not_modify_other_worktrees(self):
        self.fixture.git('config', 'extensions.worktreeConfig', 'true')
        linked = Path(self.fixture.temp.name) / 'linked'
        self.fixture.git('worktree', 'add', '-qb', 'contributor-linked', str(linked))
        common = (self.root / '.git/config').read_bytes()
        result = self.call('bootstrap', root=linked)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['hooks']['scope'], 'worktree')
        self.assertEqual((self.root / '.git/config').read_bytes(), common)
        self.assertNotEqual(self.fixture.git('config', '--get', 'core.hooksPath', ok=False).returncode, 0)
        configured = subprocess.check_output(['git', '-C', str(linked), 'config', '--worktree', '--get', 'core.hooksPath'], text=True)
        self.assertEqual(configured.strip(), 'githooks')

    def test_configuration_lock_failure_preserves_existing_config(self):
        config = (self.root / '.git/config').read_bytes()
        lock = self.fixture.write('.git/config.lock', 'other writer')
        result = self.call('hooks-install')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / '.git/config').read_bytes(), config)
        self.assertEqual(lock.read_text(), 'other writer')

    def test_global_hooks_are_preserved_and_only_the_clone_selects_replacement(self):
        global_config = Path(self.fixture.temp.name) / 'global-config'
        global_config.write_text('[core]\n\thooksPath = shared-hooks\n[custom]\n\tsetting = preserve\n')
        env = {**os.environ, 'GIT_CONFIG_GLOBAL': str(global_config), 'GIT_CONFIG_NOSYSTEM': '1'}
        before = global_config.read_bytes()
        refused = self.call('bootstrap', env=env)
        self.assertNotEqual(refused.returncode, 0)
        configured = self.call('bootstrap', '--replace-hooks', env=env)
        self.assertEqual(configured.returncode, 0, configured.stderr)
        self.assertEqual(global_config.read_bytes(), before)
        self.assertEqual(self.fixture.git('config', '--local', '--get', 'core.hooksPath').stdout.strip(), 'githooks')

    def test_command_line_hook_override_rolls_back_local_selection(self):
        before = self.fixture.git('config', '--local', '--list').stdout
        env = {**os.environ, 'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.hooksPath',
               'GIT_CONFIG_VALUE_0': 'command-line-hooks'}
        result = self.call('bootstrap', '--replace-hooks', env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('overrides', result.stderr)
        self.assertEqual(self.fixture.git('config', '--local', '--list').stdout, before)


if __name__ == '__main__':
    unittest.main()
