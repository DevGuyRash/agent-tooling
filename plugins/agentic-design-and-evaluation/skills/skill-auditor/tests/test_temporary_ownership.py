from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'


class TemporaryOwnershipTests(unittest.TestCase):
    def test_preexisting_paths_cannot_redirect_reporter_writes(self):
        for name in ('plugin_check', 'script_sanity'):
            with self.subTest(reporter=name), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                scratch=root/'scratch';scratch.mkdir()
                target=root/'target';target.mkdir()
                if name=='plugin_check':
                    for host in ('codex','claude'):
                        path=target/f'.{host}-plugin';path.mkdir()
                        (path/'plugin.json').write_text(json.dumps({'name':'target','version':'1.0.0','description':'Fixture.'}))
                    skill=target/'skills/fixture';skill.mkdir(parents=True)
                else:
                    skill=target
                (skill/'SKILL.md').write_text('---\nname: fixture\ndescription: Fixture.\n---\n# Fixture\n')
                protected=target/'protected.txt';protected.write_bytes(b'UNCHANGED FIXTURE\n')
                launch='''
for stem in plugincheck_desc scriptsanity_crlf; do
    ln -s "$3" "$TMPDIR/$stem.$$"
done
for stem in plugincheck_repo_tree plugincheck_installed_tree; do
    ln -s "$3" "$TMPDIR/$stem.$$.txt"
done
exec sh "$1" "$2" --format json
'''
                proc=subprocess.run(['sh','-c',launch,'fixture',str(SCRIPTS/(name+'.sh')),str(target),str(protected)],env={**os.environ,'TMPDIR':str(scratch)},text=True,capture_output=True)
                self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                self.assertEqual(protected.read_bytes(),b'UNCHANGED FIXTURE\n')
                remaining=list(scratch.iterdir())
                self.assertEqual(len(remaining),4)
                self.assertTrue(all(p.is_symlink() for p in remaining))


if __name__=='__main__': unittest.main()
