from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]


class ReportConsumptionTests(unittest.TestCase):
    def run_fixture(self, altered, status=0, errors_only=True):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'scripts').mkdir()
            runner=root/'scripts/audit-plugins.sh'
            shutil.copyfile(REPO/'scripts/audit-plugins.sh',runner)
            reporters=root/'plugins/agentic-design-and-evaluation/skills/skill-auditor/scripts'
            reporters.mkdir(parents=True)
            target=root/'plugins/fixture/skills/fixture';target.mkdir(parents=True)
            (target/'SKILL.md').write_text('# Fixture\n')
            for name in ('plugin_check','frontmatter_check','reference_check','script_sanity'):
                data={'script':name,'error_count':0,'errors':[],'observation_count':0,'observations':[]}
                content=altered if name=='frontmatter_check' else json.dumps(data)
                code=status if name=='frontmatter_check' else 0
                # A fixture literal goes into a quoted heredoc, never shell evaluation.
                (reporters/(name+'.sh')).write_text(f"#!/usr/bin/env sh\ncat <<'REPORT_END'\n{content}\nREPORT_END\nexit {code}\n")
            return subprocess.run(['sh',str(runner),*(['--errors-only'] if errors_only else []),'fixture'],text=True,capture_output=True)

    def test_success_without_a_report_is_tool_failure(self):
        proc=self.run_fixture('CHECK SKIPPED')
        self.assertEqual(proc.returncode,1)
        self.assertIn('tool failures: 1',proc.stdout)
        self.assertIn('CHECK SKIPPED',proc.stdout)
        self.assertNotIn('result: selected structural checks passed',proc.stdout)

    def test_malformed_counts_and_wrong_identity_are_tool_failures(self):
        valid={'script':'frontmatter_check','error_count':0,'errors':[],'observation_count':0,'observations':[]}
        for changes in ({'error_count':True},{'errors':[{}]},{'script':'other'},{'observation_count':-1}):
            with self.subTest(changes=changes):
                proc=self.run_fixture(json.dumps({**valid,**changes}))
                self.assertEqual(proc.returncode,1)
                self.assertIn('tool failures: 1',proc.stdout)

    def test_valid_target_error_is_not_a_tool_failure(self):
        data={'script':'frontmatter_check','error_count':1,'errors':[{'code':'missing','subject':'frontmatter','fact':'Required metadata absent.'}],'observation_count':0,'observations':[]}
        proc=self.run_fixture(json.dumps(data),status=1)
        self.assertEqual(proc.returncode,1)
        self.assertIn('errors: 1',proc.stdout)
        self.assertIn('tool failures: 0',proc.stdout)
        self.assertIn('Required metadata absent.',proc.stdout)

    def test_valid_report_with_contradicting_exit_status_is_tool_failure(self):
        data={'script':'frontmatter_check','error_count':0,'errors':[],'observation_count':0,'observations':[]}
        proc=self.run_fixture(json.dumps(data),status=1)
        self.assertEqual(proc.returncode,1)
        self.assertIn('tool failures: 1',proc.stdout)

    def test_valid_observation_remains_non_gating(self):
        data={'script':'frontmatter_check','error_count':0,'errors':[],'observation_count':1,'observations':[{'code':'size','subject':'file','fact':'OBSERVATION_DETAIL'}]}
        proc=self.run_fixture(json.dumps(data))
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        self.assertIn('observations: 1',proc.stdout)
        self.assertNotIn('OBSERVATION_DETAIL',proc.stdout)


if __name__=='__main__': unittest.main()
