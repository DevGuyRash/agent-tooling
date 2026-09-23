"""The compatibility CLI delegates delivery to ordinary artifact tasks."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from scripts.tests import test_artifacts as artifact_fixtures

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import package_skills
import rust_release
from artifact_sync.model import ArtifactError, load_manifest


class PackagingCommandsTests(unittest.TestCase):
    def setUp(self):
        # Reuse fixture helpers, without running the artifact suite a second time.
        self.fixture = artifact_fixtures.ArtifactTasksTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        scripts = self.root / 'scripts'
        scripts.mkdir()
        for name in ['package_skills.py', 'artifacts.py', 'rust_release.py']:
            shutil.copy2(ROOT / 'scripts' / name, scripts / name)
        shutil.copytree(ROOT / 'scripts/artifact_sync', scripts / 'artifact_sync', ignore=shutil.ignore_patterns('__pycache__'))
        path = self.root / 'packaging/artifacts.toml'
        path.write_text(path.read_text() + '''
[tasks.upper.parameters.rust]
package="example"
binary="example"
skill_dir="plugins/a"
launcher="scripts/example"
platform="linux-x86_64"
[tasks.upper.parameters.rust.targets.linux-x86_64]
recipe="cargo-zigbuild"
recipe_version="0.23.4"
zig_version="0.16.0"
cargo_target="x86_64-unknown-linux-gnu"
''')
        self.cli = scripts / 'package_skills.py'

    def call(self, *args, ok=True):
        result = subprocess.run([sys.executable, '-B', str(self.cli), *args], cwd=self.fixture.temp.name, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def test_stage_and_verify_use_task_receipts_and_skip_current_outputs(self):
        self.call('stage-host', '--skill', 'upper')
        self.assertTrue((self.root / 'packaging/receipts/upper.json').exists())
        result = json.loads(self.call('stage-host').stdout)
        self.assertEqual(result['tasks'][0]['status'], 'current')
        self.call('verify-host')
        self.call('verify-complete')
        self.call('verify-target-matrix')
        self.fixture.write('seed.txt', 'changed')
        self.call('verify-host', ok=False)
        self.assertEqual((self.root / 'plugins/a/value.txt').read_text(), 'ALPHA\n')

    def test_dist_refresh_uses_staged_source_and_preserves_worktree_input(self):
        self.call('stage-host')
        self.fixture.git('add', '.')
        self.fixture.git('commit', '-qm', 'baseline')
        self.fixture.write('seed.txt', 'staged')
        self.fixture.git('add', 'seed.txt')
        self.fixture.write('seed.txt', 'unstaged')
        self.call('dist-refresh', '--source', 'index', '--stage', '--skill', 'upper')
        self.call('verify-dist-receipt')
        self.assertEqual(self.fixture.git('show', ':plugins/a/value.txt').stdout, 'STAGED')
        self.assertEqual((self.root / 'seed.txt').read_text(), 'unstaged')

    def test_prepared_import_restores_missing_bytes_and_rejects_damage(self):
        self.call('stage-host')
        prepared = Path(self.fixture.temp.name) / 'download'
        for name in ['plugins/a/value.txt', 'plugins/b/value.txt', 'packaging/receipts/upper.json']:
            target = prepared / 'job' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root / name, target)
        self.call('compare-artifacts', '--artifacts-root', str(prepared))
        (self.root / 'plugins/a/value.txt').unlink()
        result = self.call('sync-artifacts', '--artifacts-root', str(prepared))
        self.assertEqual(json.loads(result.stdout)['tasks'][0]['status'], 'imported')
        self.assertEqual((self.root / 'plugins/a/value.txt').read_text(), 'ALPHA\n')
        (prepared / 'job/plugins/a/value.txt').write_text('damaged')
        self.call('sync-artifacts', '--artifacts-root', str(prepared), ok=False)
        self.assertEqual((self.root / 'plugins/a/value.txt').read_text(), 'ALPHA\n')

    def test_prepared_receipt_cannot_override_declared_executable_mode(self):
        manifest = self.root / 'packaging/artifacts.toml'
        manifest.write_text(manifest.read_text().replace('source = "out/value.txt"', 'source = "out/value.txt"\nexecutable = true'))
        self.call('stage-host')
        prepared = Path(self.fixture.temp.name) / 'prepared'
        for name in ['plugins/a/value.txt', 'plugins/b/value.txt', 'packaging/receipts/upper.json']:
            target = prepared / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root / name, target)
        record = prepared / 'packaging/receipts/upper.json'
        data = json.loads(record.read_text())
        for name, identity in data['outputs'].items():
            identity['mode'] = '100644'
            (prepared / name).chmod(0o644)
        record.write_text(json.dumps(data))
        self.call('sync-artifacts', '--artifacts-root', str(prepared), ok=False)
        self.assertTrue(os.access(self.root / 'plugins/a/value.txt', os.X_OK))
        # The same forged metadata in a checkout cannot make verification pass.
        (self.root / 'packaging/receipts/upper.json').write_bytes(record.read_bytes())
        for name in data['outputs']:
            (self.root / name).chmod(0o644)
        self.call('verify-host', ok=False)

    def test_watch_interface_tracks_task_inputs_and_not_other_files(self):
        changed = Path(self.fixture.temp.name) / 'changed'
        changed.write_text('seed.txt\n')
        self.assertEqual(self.call('matches-changed-files', '--changed-files-file', str(changed)).stdout.strip(), 'true')
        changed.write_text('unrelated.txt\n')
        self.assertEqual(self.call('matches-changed-files', '--changed-files-file', str(changed)).stdout.strip(), 'false')
        self.assertIn('seed.txt', self.call('watch-paths').stdout)
        changed.write_text('plugins/a/scripts/example\n')
        self.assertEqual(self.call('matches-changed-files', '--changed-files-file', str(changed)).stdout.strip(), 'true')
        self.call('stage-host', '--skill', 'unknown', ok=False)

    @unittest.skipUnless(os.name == 'posix', 'native POSIX process-group termination')
    def test_termination_of_compatibility_command_stops_producer_and_removes_workspace(self):
        self.call('stage-host')
        accepted = (self.root / 'plugins/a/value.txt').read_bytes()
        marker = Path(self.fixture.temp.name) / 'producer.json'
        self.fixture.write('build.py', f"import os,json,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(json.dumps({{'pid':os.getpid(),'workspace':str(Path.cwd())}}))\nwhile True: time.sleep(.1)\n")
        process = subprocess.Popen([sys.executable, '-B', str(self.cli), 'stage-host'], cwd=self.fixture.temp.name,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(marker.exists(), 'producer did not become ready')
            child = json.loads(marker.read_text())
            process.terminate()
            _, error = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 130, error)
            self.assertNotIn('Traceback', error)
            with self.assertRaises(ProcessLookupError):
                os.kill(child['pid'], 0)
            self.assertFalse(Path(child['workspace']).exists())
            self.assertEqual((self.root / 'plugins/a/value.txt').read_bytes(), accepted)
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)

    def test_copy_compatibility_command_uses_the_same_receipt_contract(self):
        self.fixture.write('packaging/artifacts.toml', '''version=1
[tasks.copy]
inputs=["seed.txt"]
[[tasks.copy.outputs]]
source="seed.txt"
destinations=["resource.txt"]
''')
        self.call('vendor', '--sync')
        self.call('vendor')
        self.fixture.write('resource.txt', 'manual')
        self.call('vendor', ok=False)
        self.call('vendor', '--sync', ok=False)
        self.assertEqual((self.root / 'resource.txt').read_text(), 'manual')


class RustReleaseTests(unittest.TestCase):
    def test_release_environment_normalizes_paths_and_removes_interceptors(self):
        with patch.dict(os.environ, {'PATH': '/tools/dev-cache/intercepts:/usr/bin', 'CARGO_ENCODED_RUSTFLAGS': 'override'}):
            env = rust_release.build_env_for_root(Path('/isolated/source'), 'x86_64-unknown-linux-gnu')
        self.assertIn('--remap-path-prefix=/isolated/source=/workspace', env['RUSTFLAGS'])
        self.assertNotIn('dev-cache/intercepts', env['PATH'])
        self.assertNotIn('CARGO_ENCODED_RUSTFLAGS', env)
        self.assertEqual(env['CARGO_INCREMENTAL'], '0')

    def test_pinned_recipe_uses_frozen_dependency_resolution(self):
        skill = {'package': 'example', 'targets': {'linux-x86_64': {'cargo_target': 'x86_64-unknown-linux-gnu', 'recipe': 'cargo-zigbuild'}}}
        command = rust_release.build_command(skill, 'linux-x86_64')
        self.assertEqual(command[:2], ['cargo', 'zigbuild'])
        self.assertIn('--frozen', command)
        self.assertIn('x86_64-unknown-linux-gnu', command)

    def test_declared_release_tool_versions_are_enforced(self):
        skill = {'targets': {'linux-x86_64': {'recipe': 'cargo-zigbuild', 'recipe_version': '0.23.4', 'zig_version': '0.16.0'}}}
        with patch.object(rust_release, 'command_version', side_effect=['cargo-zigbuild 0.23.4', '0.16.0']):
            rust_release.verify_release_tool(skill, 'linux-x86_64')
        with patch.object(rust_release, 'command_version', return_value='cargo-zigbuild 0.22.0'):
            with self.assertRaises(SystemExit):
                rust_release.verify_release_tool(skill, 'linux-x86_64')

    def test_windows_flags_have_deterministic_link_metadata(self):
        flags = rust_release.release_rustflags(repo_root='/source', cargo_home='/cargo', rustup_home='/rustup', cargo_target='x86_64-pc-windows-msvc')
        self.assertIn('/Brepro', flags)
        self.assertIn('/timestamp:1', flags)


if __name__ == '__main__':
    unittest.main()
