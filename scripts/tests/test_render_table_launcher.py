"""Exercise launcher decisions without modifying host Cargo configuration."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'render-table.sh'


class LauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='render launcher ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.script = self.root / 'repo/scripts/render-table.sh'
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, self.script)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for command in ('dirname', 'cat'):
            (self.bin / command).symlink_to(shutil.which(command))
        self.env = {**os.environ, 'PATH': str(self.bin)}
        for key in ('CARGO_TARGET_DIR', 'CARGO_BUILD_TARGET'):
            self.env.pop(key, None)

    def executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)

    def run_launcher(self, *args):
        return subprocess.run(['/bin/sh', str(self.script), *args], input='table input\n',
                              capture_output=True, text=True, env=self.env, timeout=10)

    def fallback(self):
        self.executable(self.root / 'repo/target/release/render-table', 'cat\n')

    def test_no_cargo_default_binary_and_missing_binary(self):
        self.assertEqual(self.run_launcher().returncode, 127)
        self.fallback()
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'table input\n')

    def test_no_cargo_custom_selection_never_runs_default_binary(self):
        self.fallback()
        for key in ('CARGO_TARGET_DIR', 'CARGO_BUILD_TARGET'):
            with self.subTest(key=key):
                self.env[key] = 'custom selection'
                result = self.run_launcher()
                self.assertEqual(result.returncode, 127)
                self.assertIn('cargo is required', result.stderr)
                self.assertEqual(result.stdout, '')
                self.env.pop(key)

    def test_cargo_receives_arguments_stdin_and_environment_even_with_fallback(self):
        self.fallback()
        self.env['CARGO_TARGET_DIR'] = 'custom target with spaces'
        self.executable(self.bin / 'cargo', 'printf "%s\\n" "$@" "$CARGO_TARGET_DIR"\ncat\n')
        result = self.run_launcher('--headers', 'Two words')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['run', '--manifest-path',
            str(self.root / 'repo/Cargo.toml'), '--locked', '--release', '--quiet',
            '-p', 'render-table', '--', '--headers', 'Two words',
            'custom target with spaces', 'table input'])

    def test_cargo_failure_is_not_masked_by_stale_fallback(self):
        self.fallback()
        self.executable(self.bin / 'cargo', 'printf "build failed\\n" >&2\nexit 42\n')
        result = self.run_launcher()
        self.assertEqual(result.returncode, 42)
        self.assertEqual(result.stdout, '')
        self.assertIn('build failed', result.stderr)

@unittest.skipUnless(shutil.which('cargo'), 'Cargo required for actual target resolution')
class CargoTargetTests(unittest.TestCase):
    def test_real_cargo_environment_config_and_native_triple(self):
        with tempfile.TemporaryDirectory(prefix='render cargo ') as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            shutil.copyfile(SCRIPT, root / 'scripts/render-table.sh')
            (root / 'src').mkdir()
            (root / 'Cargo.toml').write_text('[package]\nname="render-table"\nversion="0.1.0"\nedition="2021"\n')
            (root / 'src/main.rs').write_text('fn main() { println!("selected artifact"); }\n')
            env = {**os.environ}
            for key in ('CARGO_TARGET_DIR', 'CARGO_BUILD_TARGET'):
                env.pop(key, None)
            subprocess.run(['cargo', 'generate-lockfile', '--offline'], cwd=root, env=env,
                           check=True, capture_output=True, timeout=30)
            host_info = subprocess.run(['rustc', '-vV'], env=env, capture_output=True,
                                       text=True, check=True, timeout=30).stdout
            host = next(line.removeprefix('host: ') for line in host_info.splitlines() if line.startswith('host: '))
            (root / '.cargo').mkdir()
            for selection in ('env', 'config', 'triple'):
                with self.subTest(selection=selection):
                    configured = 'configured target'
                    text = '[build]\ntarget-dir="configured target"\n'
                    if selection == 'triple':
                        text += f'target="{host}"\n'
                    (root / '.cargo/config.toml').write_text(text)
                    run_env = {**env}
                    if selection == 'env':
                        run_env['CARGO_TARGET_DIR'] = 'environment target'
                        configured = 'environment target'
                    result = subprocess.run(['sh', str(root / 'scripts/render-table.sh')], cwd=root,
                        env=run_env, capture_output=True, text=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, 'selected artifact\n')
                    binary = root / configured
                    if selection == 'triple':
                        binary /= host
                    self.assertTrue((binary / 'release/render-table').is_file())
                    self.assertFalse((root / 'target').exists())
