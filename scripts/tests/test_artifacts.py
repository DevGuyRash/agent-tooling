"""Actual commands and Git indexes exercise the artifact contract."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "scripts/artifacts.py"


class ArtifactTasksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="artifact-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Artifact fixture")
        self.git("config", "user.email", "artifact@example.invalid")
        self.write(".gitignore", ".local/\ncontext/\n")
        self.write("seed.txt", "alpha\n")
        self.write("build.py", "from pathlib import Path\np=Path('out');p.mkdir(exist_ok=True)\np.joinpath('value.txt').write_text(Path('seed.txt').read_text().upper())\n")
        self.write_manifest()
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def git(self, *args, env=None, ok=True, data=None):
        p = subprocess.run(["git", "-C", str(self.root), *args], env=env, input=data,
                           text=True, capture_output=True)
        if ok:
            self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def call(self, operation="sync", *flags, ok=True, env=None, stdin=None):
        p = subprocess.run([sys.executable, "-B", str(CLI), "--repo", str(self.root), operation, *flags],
                           cwd=self.temp.name, text=True, input=stdin, capture_output=True, env=env, timeout=40)
        if ok:
            self.assertEqual(p.returncode, 0, p.stderr)
            return json.loads(p.stdout)
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("Traceback", p.stderr)
        return p

    def write_manifest(self, addition="", *, command=True):
        text = '''version = 1
[tasks.upper]
inputs = ["seed.txt", "build.py"]
'''
        if command:
            text += 'command = ["{python}", "build.py"]\n'
        text += '''[[tasks.upper.outputs]]
source = "out/value.txt"
destinations = ["plugins/a/value.txt", "plugins/b/value.txt"]
'''
        self.write("packaging/artifacts.toml", text + addition)

    def test_fanout_current_check_and_content_not_mtime(self):
        initial = self.call()
        self.assertEqual(initial["tasks"][0]["status"], "executed")
        self.assertEqual((self.root / "plugins/a/value.txt").read_text(), "ALPHA\n")
        self.assertEqual((self.root / "plugins/a/value.txt").read_bytes(),
                         (self.root / "plugins/b/value.txt").read_bytes())
        before = (self.root / "packaging/receipts/upper.json").read_bytes()
        os.utime(self.root / "seed.txt", (1, 1))
        self.assertEqual(self.call()["tasks"][0]["status"], "current")
        self.assertEqual(self.call("check")["tasks"][0]["status"], "current")
        self.assertEqual(before, (self.root / "packaging/receipts/upper.json").read_bytes())
        self.write("seed.txt", "beta\n")
        self.assertEqual(self.call("check", ok=False).returncode, 1)
        self.call()
        self.assertEqual((self.root / "plugins/a/value.txt").read_text(), "BETA\n")

    def test_unrelated_task_definition_does_not_invalidate(self):
        self.call()
        self.write("other.txt", "Other material")
        extra = '''
[tasks.other]
inputs = ["other.txt"]
[[tasks.other.outputs]]
source = "other.txt"
destinations = ["plugins/c/other.txt"]
'''
        self.write_manifest(extra)
        result = self.call()
        self.assertEqual([r["status"] for r in result["tasks"]], ["current", "executed"])
        self.assertEqual((self.root / "plugins/c/other.txt").read_text(), "Other material")

    def test_glob_additions_deletions_and_renames_change_inputs(self):
        self.write("parts/a.txt", "A")
        self.write("combine.py", "from pathlib import Path\nPath('result.txt').write_text('|'.join(p.name+':'+p.read_text() for p in sorted(Path('parts').rglob('*.txt'))))\n")
        self.write("packaging/artifacts.toml", '''version=1
[tasks.join]
inputs=["parts/**/*.txt", "combine.py"]
command=["{python}", "combine.py"]
[[tasks.join.outputs]]
source="result.txt"
destinations=["out/result.txt"]
''')
        self.call()
        self.assertEqual((self.root/"out/result.txt").read_text(), "a.txt:A")
        self.write("parts/sub/b.txt", "B")
        self.call()
        self.assertEqual((self.root/"out/result.txt").read_text(), "a.txt:A|b.txt:B")
        (self.root/"parts/a.txt").rename(self.root/"parts/c.txt")
        (self.root/"parts/sub/b.txt").unlink()
        self.call()
        self.assertEqual((self.root/"out/result.txt").read_text(), "c.txt:A")

    def test_unchanged_dependency_content_skips_downstream(self):
        self.write("consume.py", "from pathlib import Path\nPath('answer.txt').write_text(Path('plugins/a/value.txt').read_text()+'Consumed\\n')\n")
        extra = '''
[tasks.consume]
inputs=["plugins/a/value.txt", "consume.py"]
needs=["upper"]
command=["{python}", "consume.py"]
[[tasks.consume.outputs]]
source="answer.txt"
destinations=["plugins/c/answer.txt"]
'''
        self.write_manifest(extra)
        self.call()
        self.write("seed.txt", "ALPHA\n")
        result = self.call()
        self.assertEqual([r["status"] for r in result["tasks"]], ["executed", "current"])
        self.assertEqual((self.root/"plugins/c/answer.txt").read_text(), "ALPHA\nConsumed\n")

    def test_missing_output_regenerates_and_manual_edit_is_protected(self):
        self.call()
        (self.root/"plugins/a/value.txt").unlink()
        self.assertEqual(self.call()["tasks"][0]["status"], "executed")
        self.write("plugins/a/value.txt", "Manual material")
        failed = self.call(ok=False)
        self.assertIn("manual changes", failed.stderr)
        self.assertEqual((self.root/"plugins/a/value.txt").read_text(), "Manual material")
        self.call("sync", "--replace")
        self.assertEqual((self.root/"plugins/a/value.txt").read_text(), "ALPHA\n")

    def test_failure_preserves_previous_outputs_and_receipt(self):
        self.call()
        before = {name: (self.root/name).read_bytes() for name in
                  ["plugins/a/value.txt", "plugins/b/value.txt", "packaging/receipts/upper.json"]}
        self.write("build.py", "from pathlib import Path\nPath('out').mkdir();Path('out/value.txt').write_text('partial')\nraise SystemExit(7)\n")
        failure = self.call(ok=False)
        self.assertIn("exited 7", failure.stderr)
        for name, data in before.items():
            self.assertEqual((self.root/name).read_bytes(), data)

    def test_missing_prerequisite_reports_recovery(self):
        self.write_manifest()
        file = self.root/"packaging/artifacts.toml"
        file.write_text(file.read_text().replace('[tasks.upper]', '[tasks.upper]\ntools=["unavailable-artifact-test-tool-847201"]'))
        p=self.call(ok=False)
        self.assertIn("required tool is unavailable",p.stderr)
        self.assertFalse((self.root/"plugins/a/value.txt").exists())

    def test_input_changed_during_command_refuses_publication(self):
        self.write("build.py", f"from pathlib import Path\nPath('out').mkdir();Path('out/value.txt').write_text('candidate')\nPath({str(self.root/'seed.txt')!r}).write_text('Concurrent source edit')\n")
        self.call(ok=False)
        self.assertFalse((self.root/"plugins/a/value.txt").exists())
        self.assertEqual((self.root/"seed.txt").read_text(), "Concurrent source edit")

    def test_ownership_collisions_and_cycles_refused_before_commands(self):
        for extra in ('''
[tasks.conflict]
inputs=["seed.txt"]
[[tasks.conflict.outputs]]
source="seed.txt"
destinations=["plugins/a/value.txt"]
''', '''
[tasks.cycle]
inputs=["seed.txt"]
needs=["cycle"]
[[tasks.cycle.outputs]]
source="seed.txt"
destinations=["elsewhere.txt"]
'''):
            self.write_manifest(extra)
            self.call(ok=False)
            self.assertFalse((self.root/"plugins/a/value.txt").exists())

    def test_source_modes_and_direct_materialization(self):
        self.write("helper.py", "print('ready')\n").chmod(0o755)
        self.write("packaging/artifacts.toml", '''version=1
[tasks.helper]
inputs=["helper.py"]
[[tasks.helper.outputs]]
source="helper.py"
destinations=["plugins/a/scripts/helper.py","plugins/b/scripts/helper.py"]
''')
        self.call()
        for path in ["plugins/a/scripts/helper.py","plugins/b/scripts/helper.py"]:
            self.assertTrue(os.access(self.root/path,os.X_OK))
            p=subprocess.run([sys.executable,str(self.root/path)],capture_output=True,text=True)
            self.assertEqual(p.stdout,"ready\n")
        self.write("helper.py", "print('changed')\n").chmod(0o644)
        self.call()
        self.assertFalse(os.access(self.root/"plugins/a/scripts/helper.py", os.X_OK))

    def staged_fixture(self):
        self.call()
        self.git("add", ".")
        self.git("commit", "-qm", "generated baseline")

    def test_index_generation_preserves_partial_staging(self):
        self.staged_fixture()
        self.write("seed.txt","staged\n");self.git("add","seed.txt")
        self.write("seed.txt","unstaged\n")
        self.write("unrelated.txt","keep staged\n");self.git("add","unrelated.txt")
        self.write("unrelated.txt","keep unstaged\n")
        self.call("sync","--source","index","--stage")
        self.assertEqual(self.git("show",":plugins/a/value.txt").stdout,"STAGED\n")
        self.assertEqual(self.git("show",":seed.txt").stdout,"staged\n")
        self.assertEqual((self.root/"seed.txt").read_text(),"unstaged\n")
        self.assertEqual(self.git("show",":unrelated.txt").stdout,"keep staged\n")
        self.assertEqual((self.root/"unrelated.txt").read_text(),"keep unstaged\n")
        self.call("check","--source","index")

    def test_manual_unstaged_output_edit_is_not_overwritten(self):
        self.staged_fixture()
        self.write("seed.txt","staged\n");self.git("add","seed.txt")
        self.write("plugins/a/value.txt","manual output")
        index=(self.root/".git/index").read_bytes()
        self.call("sync","--source","index","--stage",ok=False)
        self.assertEqual((self.root/".git/index").read_bytes(),index)
        self.assertEqual((self.root/"plugins/a/value.txt").read_text(),"manual output")

    def test_prepared_worktree_outputs_can_be_staged_with_their_matching_inputs(self):
        self.staged_fixture()
        self.write('seed.txt', 'prepared\n')
        self.call()
        self.git('add', 'seed.txt')
        self.call('pre-commit')
        self.assertEqual(self.git('show', ':plugins/a/value.txt').stdout, 'PREPARED\n')
        self.call('check', '--source', 'index')

    def test_partial_commit_refuses_generation_before_mutating_either_index(self):
        self.staged_fixture()
        scripts = self.root / 'scripts'
        scripts.mkdir()
        shutil.copy2(CLI, scripts / 'artifacts.py')
        shutil.copytree(REPO / 'scripts/artifact_sync', scripts / 'artifact_sync', ignore=shutil.ignore_patterns('__pycache__'))
        hooks = self.root / 'githooks'
        hooks.mkdir()
        shutil.copy2(REPO / 'githooks/pre-commit', hooks / 'pre-commit')
        self.git('config', 'core.hooksPath', 'githooks')
        before = self.git('rev-parse', 'HEAD').stdout
        entries = self.git('ls-files', '--stage').stdout
        self.write('seed.txt', 'partial\n')
        result = self.git('commit', '--only', '-qm', 'partial commit', '--', 'seed.txt', ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('second locked index', result.stderr)
        self.assertEqual(self.git('rev-parse', 'HEAD').stdout, before)
        self.assertEqual(self.git('ls-files', '--stage').stdout, entries)
        self.assertEqual((self.root / 'plugins/a/value.txt').read_text(), 'ALPHA\n')
        self.git('add', 'seed.txt')
        self.git('commit', '-qm', 'regular commit')
        self.assertEqual(self.git('show', 'HEAD:plugins/a/value.txt').stdout, 'PARTIAL\n')
        self.assertEqual(self.git('diff', '--cached', '--name-only').stdout, '')

    def test_alternate_index_is_used_without_changing_default_index(self):
        self.staged_fixture()
        alternate=Path(self.temp.name)/"alternate-index"
        shutil.copy2(self.root/".git/index",alternate)
        env={**os.environ,"GIT_INDEX_FILE":str(alternate)}
        self.write("seed.txt","alternate\n");self.git("add","seed.txt",env=env)
        default=(self.root/".git/index").read_bytes()
        self.call("sync","--source","index","--stage",env=env)
        self.assertEqual(self.git("show",":plugins/a/value.txt",env=env).stdout,"ALTERNATE\n")
        self.assertEqual((self.root/".git/index").read_bytes(),default)

    def test_foreign_index_lock_is_preserved(self):
        self.staged_fixture()
        self.write("seed.txt","staged\n");self.git("add","seed.txt")
        lock=self.write(".git/index.lock","unrelated Git lock")
        self.call("sync","--source","index","--stage",ok=False)
        self.assertEqual(lock.read_text(),"unrelated Git lock")

    def test_relative_alternate_index_from_unrelated_directory(self):
        self.staged_fixture()
        shutil.copy2(self.root / '.git/index', self.root / '.git/alternate')
        env = {**os.environ, 'GIT_INDEX_FILE': '.git/alternate'}
        self.write('seed.txt', 'relative\n')
        self.git('add', 'seed.txt', env=env)
        ordinary = (self.root / '.git/index').read_bytes()
        self.call('pre-commit', env=env)
        self.assertEqual(self.git('show', ':plugins/a/value.txt', env=env).stdout, 'RELATIVE\n')
        self.assertEqual((self.root / '.git/index').read_bytes(), ordinary)

    def test_receipt_cannot_omit_a_declared_destination(self):
        self.call()
        path = self.root / 'packaging/receipts/upper.json'
        record = json.loads(path.read_text())
        del record['outputs']['plugins/b/value.txt']
        path.write_text(json.dumps(record))
        (self.root / 'plugins/b/value.txt').unlink()
        self.call('check', ok=False)
        self.assertEqual(self.call()['tasks'][0]['status'], 'executed')
        self.assertEqual((self.root / 'plugins/b/value.txt').read_text(), 'ALPHA\n')

    def test_current_dependency_output_change_refuses_child_publication(self):
        self.call()
        self.write('consume.py', f"from pathlib import Path\nPath('result').write_text(Path('plugins/a/value.txt').read_text())\nPath({str(self.root / 'plugins/a/value.txt')!r}).write_text('manual edit')\n")
        self.write_manifest('''
[tasks.child]
inputs=["consume.py", "plugins/a/value.txt"]
needs=["upper"]
command=["{python}", "consume.py"]
[[tasks.child.outputs]]
source="result"
destinations=["child.txt"]
''')
        previous = (self.root / 'packaging/receipts/upper.json').read_bytes()
        self.assertIn('changed during preparation', self.call(ok=False).stderr)
        self.assertFalse((self.root / 'child.txt').exists())
        self.assertFalse((self.root / 'packaging/receipts/child.json').exists())
        self.assertEqual((self.root / 'plugins/a/value.txt').read_text(), 'manual edit')
        self.assertEqual((self.root / 'packaging/receipts/upper.json').read_bytes(), previous)

    def test_directory_membership_change_during_command_is_preserved(self):
        self.write('packaging/artifacts.toml', '''version=1
[tasks.copy]
inputs=["seed.txt"]
[[tasks.copy.outputs]]
source="seed.txt"
destinations=["parent/value.txt"]
[tasks.child]
inputs=["build.py", "parent/value.txt"]
needs=["copy"]
command=["{python}", "build.py"]
[[tasks.child.outputs]]
source="out"
directory=true
destinations=["child"]
''')
        self.write('build.py', 'from pathlib import Path\nPath("out").mkdir();Path("out/a").write_text("A")\n')
        self.call()
        self.write('build.py', f'from pathlib import Path\nPath("out").mkdir();Path("out/a").write_text("B")\nPath({str(self.root / "child/manual")!r}).write_text("keep")\n')
        self.call(ok=False)
        self.assertEqual((self.root / 'child/manual').read_text(), 'keep')
        self.assertEqual((self.root / 'child/a').read_text(), 'A')

    def test_exception_after_index_rename_preserves_replacement_lock(self):
        self.staged_fixture()
        self.write('seed.txt', 'new\n')
        self.git('add', 'seed.txt')
        script = f'''import sys
from pathlib import Path
sys.path.insert(0, {str(REPO / 'scripts')!r})
from artifact_sync import publish, engine
root = Path({str(self.root)!r})
original = publish.os.replace
def replacement(source, destination):
    original(source, destination)
    if Path(destination) == root / '.git/index':
        (root / '.git/index.lock').write_bytes(b'foreign replacement')
        raise KeyboardInterrupt()
publish.os.replace = replacement
try:
    engine.sync(root, source='index', stage=True)
except BaseException:
    pass
assert (root / '.git/index.lock').read_bytes() == b'foreign replacement'
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('show', ':plugins/a/value.txt').stdout, 'NEW\n')
        (self.root / '.git/index.lock').unlink()
        self.call('sync', '--source', 'index', '--stage')
        self.call('check', '--source', 'index')

    def test_released_lock_is_not_cleaned_up_twice(self):
        self.staged_fixture()
        self.write('seed.txt', 'new\n')
        self.git('add', 'seed.txt')
        script = f'''import sys
from pathlib import Path
sys.path.insert(0, {str(REPO / 'scripts')!r})
from artifact_sync import publish, engine
root = Path({str(self.root)!r})
original = publish.unlink_owned_lock
releases = []
def release(path, identity):
    if identity is not None:
        releases.append(identity)
    original(path, identity)
publish.unlink_owned_lock = release
publish.git = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('interrupted')) if 'update-index' in args else original_git(*args, **kwargs)
original_git = __import__('artifact_sync.snapshots', fromlist=['git']).git
try:
    engine.sync(root, source='index', stage=True)
except RuntimeError:
    pass
assert len(releases) == 1, releases
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git('show', ':plugins/a/value.txt').stdout, 'ALPHA\n')

    def test_real_hook_rejects_a_push_of_a_stale_other_branch(self):
        self.staged_fixture()
        scripts = self.root / 'scripts'
        scripts.mkdir()
        shutil.copy2(CLI, scripts / 'artifacts.py')
        shutil.copytree(REPO / 'scripts/artifact_sync', scripts / 'artifact_sync', ignore=shutil.ignore_patterns('__pycache__'))
        hooks = self.root / 'githooks'
        hooks.mkdir()
        shutil.copy2(REPO / 'githooks/pre-push', hooks / 'pre-push')
        self.git('config', 'core.hooksPath', 'githooks')
        remote = Path(self.temp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
        self.git('remote', 'add', 'fixture', str(remote))
        good = self.git('rev-parse', 'HEAD').stdout.strip()
        self.git('push', '-q', 'fixture', 'HEAD:refs/heads/good')
        self.git('checkout', '-qb', 'stale-push')
        self.write('seed.txt', 'stale')
        self.git('add', 'seed.txt')
        self.git('commit', '-qm', 'stale branch')
        self.git('checkout', '-q', '-')
        refused = self.git('push', '-q', 'fixture', 'stale-push:refs/heads/stale', ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('changed inputs', refused.stderr)
        self.assertEqual(self.git('ls-remote', 'fixture', 'refs/heads/stale').stdout, '')
        self.assertIn(good, self.git('ls-remote', 'fixture', 'refs/heads/good').stdout)

    def test_real_commit_and_amend_run_generation_hook(self):
        self.staged_fixture()
        hook=self.write(".git/hooks/pre-commit", f"#!/bin/sh\nexec '{sys.executable}' -B '{CLI}' --repo '{self.root}' pre-commit\n")
        hook.chmod(0o755)
        self.write("seed.txt","hook\n");self.git("add","seed.txt")
        self.git("commit","-qm","hook-generated")
        self.assertEqual(self.git("show","HEAD:plugins/a/value.txt").stdout,"HOOK\n")
        self.write("seed.txt","amended\n");self.git("add","seed.txt")
        self.git("commit","--amend","--no-edit","-q")
        self.assertEqual(self.git("show","HEAD:plugins/a/value.txt").stdout,"AMENDED\n")

    def test_outgoing_other_branch_checked_instead_of_worktree(self):
        self.staged_fixture()
        good=self.git("rev-parse","HEAD").stdout.strip()
        self.git("checkout","-qb","stale")
        self.write("seed.txt","stale branch\n");self.git("add","seed.txt");self.git("commit","-qm","stale")
        bad=self.git("rev-parse","HEAD").stdout.strip()
        self.git("checkout","-q","-")
        self.call("pre-push",stdin=f"refs/heads/main {good} refs/heads/main {'0'*40}\n")
        p=self.call("pre-push",stdin=f"refs/heads/stale {bad} refs/heads/stale {'0'*40}\n",ok=False)
        self.assertIn("changed inputs",p.stderr)
        self.assertEqual((self.root/"seed.txt").read_text(),"alpha\n")

    def test_globs_respect_directory_segments(self):
        self.write("parts/a.txt","A")
        self.write("parts/nested/b.txt","B")
        self.write("packaging/artifacts.toml", '''version=1
[tasks.copy]
inputs=["parts/*.txt"]
[[tasks.copy.outputs]]
source="parts"
directory=true
destinations=["out"]
''')
        self.call()
        self.assertEqual((self.root/"out/a.txt").read_text(),"A")
        self.assertFalse((self.root/"out/nested/b.txt").exists())
        self.write("parts/nested/b.txt","changed but outside selection")
        self.assertEqual(self.call()["tasks"][0]["status"],"current")

    def test_explicit_refresh_is_separate_from_automatic_tasks(self):
        self.write_manifest('''
[tasks.refresh]
automatic=false
cache=false
inputs=["seed.txt"]
command=["{python}", "-c", "raise SystemExit(41)"]
[[tasks.refresh.outputs]]
source="new.txt"
destinations=["captured.txt"]
''')
        self.call()
        self.assertIn("exited 41",self.call("sync","--task","refresh",ok=False).stderr)

    def test_directory_extra_file_is_preserved_as_a_conflict(self):
        self.write("src/a.py","print('ok')\n")
        self.write("packaging/artifacts.toml", '''version=1
[tasks.copy]
inputs=["src"]
[[tasks.copy.outputs]]
source="src"
directory=true
destinations=["pkg/scripts"]
''')
        self.call()
        self.write("pkg/scripts/manual.py","user material")
        self.call("check",ok=False)
        self.assertIn("unowned file",self.call(ok=False).stderr)
        self.assertEqual((self.root/"pkg/scripts/manual.py").read_text(),"user material")

    def test_ignored_preview_and_its_local_receipt_can_be_current(self):
        self.write("packaging/artifacts.toml", '''version=1
[tasks.preview]
automatic=false
inputs=["seed.txt"]
receipt=".local/context/preview.receipt.json"
[[tasks.preview.outputs]]
source="seed.txt"
destinations=[".local/context/preview/value.txt"]
''')
        self.call("sync","--task","preview")
        self.assertEqual(self.call("sync","--task","preview")["tasks"][0]["status"],"current")

    def test_fresh_clone_can_verify_committed_receipts(self):
        self.staged_fixture()
        clone=Path(self.temp.name)/"clone"
        subprocess.run(["git","clone","-q","--local",str(self.root),str(clone)],check=True)
        result=subprocess.run([sys.executable,"-B",str(CLI),"--repo",str(clone),"check"],
                              cwd=self.temp.name,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["tasks"][0]["status"],"current")

    def test_linked_worktree_uses_its_index_and_files(self):
        self.staged_fixture()
        linked=Path(self.temp.name)/"linked"
        self.git("worktree","add","-qb","linked",str(linked))
        (linked/"seed.txt").write_text("linked\n")
        subprocess.run(["git","-C",str(linked),"add","seed.txt"],check=True)
        result=subprocess.run([sys.executable,"-B",str(CLI),"--repo",str(linked),"sync","--source","index","--stage"],
                              cwd=self.temp.name,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        value=subprocess.check_output(["git","-C",str(linked),"show",":plugins/a/value.txt"],text=True)
        self.assertEqual(value,"LINKED\n")
        self.assertEqual((self.root/"plugins/a/value.txt").read_text(),"ALPHA\n")

    def test_concurrent_preparations_leave_one_complete_result(self):
        self.write("build.py","import time\nfrom pathlib import Path\ntime.sleep(.2)\nPath('out').mkdir()\nPath('out/value.txt').write_text(Path('seed.txt').read_text().upper())\n")
        commands=[[sys.executable,"-B",str(CLI),"--repo",str(self.root),"sync"] for _ in range(2)]
        processes=[subprocess.Popen(command,cwd=self.temp.name,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for command in commands]
        records=[(p,p.communicate(timeout=30)) for p in processes]
        self.assertTrue(any(p.returncode==0 for p,_ in records))
        for p,(_out,err) in records:
            self.assertIn(p.returncode,[0,2],err)
            self.assertNotIn("Traceback",err)
        self.call("check")
        self.assertEqual((self.root/"plugins/a/value.txt").read_bytes(),(self.root/"plugins/b/value.txt").read_bytes())

    def test_interrupted_index_publication_recovers_before_retry(self):
        self.staged_fixture()
        self.write("seed.txt","recovered\n");self.git("add","seed.txt")
        script = f"""import sys,os
from pathlib import Path
sys.path.insert(0,{str(REPO/'scripts')!r})
from artifact_sync import publish,engine
root=Path({str(self.root)!r})
original=publish.write_item
def stop_after(root_arg,name,item):
    original(root_arg,name,item)
    if root_arg==root and name=='plugins/a/value.txt':
        os._exit(77)
publish.write_item=stop_after
engine.sync(root,source='index',stage=True)
"""
        result=subprocess.run([sys.executable,"-B","-c",script],cwd=self.temp.name,capture_output=True,text=True)
        self.assertEqual(result.returncode,77,result.stderr)
        self.assertEqual(self.git("show",":plugins/a/value.txt").stdout,"ALPHA\n")
        self.call("sync","--source","index","--stage")
        self.assertEqual(self.git("show",":plugins/a/value.txt").stdout,"RECOVERED\n")
        self.assertEqual(self.git("show",":plugins/b/value.txt").stdout,"RECOVERED\n")
        self.assertFalse((self.root/".git/artifact-publication").exists())
        self.assertFalse((self.root/".git/index.lock").exists())
        self.assertEqual(list((self.root/".git").glob("artifact-index-*")),[])


if __name__ == "__main__":
    unittest.main()
