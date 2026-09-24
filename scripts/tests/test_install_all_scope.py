"""Process-level scope and cross-host preservation counterexamples."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from scripts.install_all import discover, receipt_identity

REPO=Path(__file__).resolve().parents[2]
PLUGIN='target@agent-tooling'
KEEP='keep@elsewhere'

FAKE=r'''import json,os,sys
from pathlib import Path
name=Path(__file__).name
root=Path(os.environ['FIXTURE_ROOT'])
args=sys.argv[1:]
with (root/'calls.jsonl').open('a') as log:log.write(json.dumps({'host':name,'args':args})+'\n')
registry=root/'profile/plugins/installed_plugins.json'
codex=root/'codex.json'
def read(path):return json.loads(path.read_text())
def write(path,data):path.write_text(json.dumps(data))
if args==['plugin','marketplace','list','--json']:
    rows=[{'name':'agent-tooling','source':str(root/'repo')}]
    print(json.dumps({'marketplaces':rows} if name=='codex' else rows))
elif args==['plugin','list','--json']:
    if name=='codex':print(json.dumps({'installed':read(codex)}))
    else:
        rows=[{'pluginId':key,'enabled':True,**entry} for key,entries in read(registry)['plugins'].items() for entry in entries]
        print(json.dumps(rows))
elif args[:2]==['plugin','uninstall']:
    scope=args[args.index('--scope')+1]
    project=os.getcwd() if scope!='user' else None
    data=read(registry)
    data['plugins']['target@agent-tooling']=[e for e in data['plugins'].get('target@agent-tooling',[])
        if (e.get('scope'),e.get('projectPath'))!=(scope,project)]
    write(registry,data)
elif args[:2] in (['plugin','add'],['plugin','install'],['plugin','update']):
    scope=args[args.index('--scope')+1] if '--scope' in args else 'user'
    if os.environ.get('FAULT')=='wrong-user' and name=='claude':scope='project'
    entry={'version':'1.0.0','installPath':str(root/'repo/plugins/target'),'scope':scope}
    if scope!='user':entry['projectPath']=os.getcwd()
    if name=='codex':
        write(codex,[{'pluginId':'target@agent-tooling','enabled':True,**entry}])
        if os.environ.get('FAULT') in ('drop-all','drop-keep'):
            data=read(registry)
            data['plugins']={} if os.environ['FAULT']=='drop-all' else {k:v for k,v in data['plugins'].items() if k=='target@agent-tooling'}
            write(registry,data)
    else:
        data=read(registry)
        entries=data['plugins'].get('target@agent-tooling',[])
        if os.environ.get('FAULT')=='drop-project':entries=[]
        entries=[e for e in entries if (e.get('scope'),e.get('projectPath'))!=(entry.get('scope'),entry.get('projectPath'))]
        data['plugins']['target@agent-tooling']=entries+[entry]
        write(registry,data)
else:raise SystemExit('unexpected call '+str(args))
'''


class InstallerScopeProcessTests(unittest.TestCase):
    def run_case(self, *, codex_current=False, claude_current=False, fault='', scope='user', force=False, dry=False, version=2, other_project=False, only_other_scope=False, claude_only=False):
        with tempfile.TemporaryDirectory(prefix='install-scope-') as tmp:
            root=Path(tmp);repo=root/'repo';(repo/'scripts').mkdir(parents=True)
            for name in ('install-all','install_all.py'):shutil.copy2(REPO/'scripts'/name,repo/'scripts'/name)
            package=repo/'plugins/target'
            for host in ('codex','claude'):
                folder=package/f'.{host}-plugin';folder.mkdir(parents=True)
                (folder/'plugin.json').write_text(json.dumps({'name':'target','version':'1.0.0','description':'Fixture.'}))
                catalog=repo/('.agents/plugins' if host=='codex' else '.claude-plugin')/'marketplace.json';catalog.parent.mkdir(parents=True,exist_ok=True)
                source={'source':'local','path':'./plugins/target'} if host=='codex' else './plugins/target'
                catalog.write_text(json.dumps({'name':'agent-tooling','plugins':[{'name':'target','source':source}]}))
            work=root/'project/nested';work.mkdir(parents=True)
            profile=root/'profile';(profile/'plugins').mkdir(parents=True)
            current={'scope':scope,'version':'1.0.0','installPath':str(package)}
            if scope!='user':current['projectPath']=str(work)
            keeper={'scope':'user','version':'7.0.0','installPath':'/fixture/keep','gitCommitSha':'b'*40}
            entries={KEEP:[keeper]}
            if claude_current:entries[PLUGIN]=[current]
            if other_project:
                entries.setdefault(PLUGIN,[]).append({**current,'scope':scope,'projectPath':str(root/'other-project'),'opaque':'retain'})
            if only_other_scope:
                entries[PLUGIN]=[{**current,'scope':'project','projectPath':str(root/'other-project'),'opaque':'retain'}]
            before={'version':version,'plugins':entries}
            registry=profile/'plugins/installed_plugins.json';registry.write_text(json.dumps(before))
            original=registry.read_bytes()
            (root/'codex.json').write_text(json.dumps([{'pluginId':PLUGIN,'version':'1.0.0','installPath':str(package)}] if codex_current else []))
            binary=root/'bin';binary.mkdir()
            for name in ('codex','claude'):
                path=binary/name;path.write_text(f'#!{sys.executable}\n'+FAKE);path.chmod(0o755)
            env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],'FIXTURE_ROOT':str(root),'CLAUDE_CONFIG_DIR':str(profile),'CODEX_HOME':str(root/'codex-profile'),'XDG_STATE_HOME':str(root/'state'),'FAULT':fault}
            argv=[str(repo/'scripts/install-all'),'--source',str(repo),'--include','target','--claude-scope',scope]
            if claude_only:argv+=['--claude-only']
            if force:argv+=['--force']
            if dry:argv+=['--dry-run']
            proc=subprocess.run(argv,cwd=work,env=env,text=True,capture_output=True)
            after=json.loads(registry.read_text())
            calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
            mutations=[c for c in calls if c['args'][:2] in (['plugin','add'],['plugin','install'],['plugin','update'],['plugin','uninstall'])]
            receipt=root/'state/agent-tooling/install-all.json'
            return proc,before,after,mutations,(json.loads(receipt.read_text()) if receipt.exists() else None),registry.read_bytes()==original,str(work)

    def test_mixed_host_noop_preserves_all_claude_records(self):
        for fault in ('drop-keep','drop-all'):
            with self.subTest(fault=fault):
                proc,before,after,calls,receipt,_,_=self.run_case(claude_current=True,fault=fault)
                self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                self.assertEqual(after,before)
                self.assertEqual([c['host'] for c in calls],['codex'])
                self.assertTrue(receipt)

    def test_both_hosts_mutating_preserves_unrelated_control(self):
        proc,before,after,calls,receipt,_,_=self.run_case(fault='drop-all')
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        self.assertEqual(after['plugins'][KEEP],before['plugins'][KEEP])
        self.assertIn(PLUGIN,after['plugins'])
        self.assertEqual([c['host'] for c in calls],['codex','claude'])
        self.assertTrue(receipt)

    def test_unsupported_registry_blocks_mixed_host_before_mutation(self):
        proc,_,_,calls,receipt,unchanged,_=self.run_case(claude_current=True,version=3,fault='drop-all')
        self.assertNotEqual(proc.returncode,0)
        self.assertEqual(calls,[])
        self.assertFalse(receipt)
        self.assertTrue(unchanged)

    def test_complete_noop_and_dry_run_leave_registry_unchanged(self):
        for dry in (False,True):
            with self.subTest(dry=dry):
                proc,_,_,calls,receipt,unchanged,_=self.run_case(codex_current=not dry,claude_current=True,dry=dry,fault='drop-all')
                self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                self.assertEqual(calls,[])
                self.assertTrue(unchanged)
                self.assertEqual(bool(receipt),not dry)

    def test_other_project_same_scope_is_preserved(self):
        for scope in ('project','local'):
            with self.subTest(scope=scope):
                proc,before,after,_,receipt,_,work=self.run_case(claude_current=True,other_project=True,scope=scope,force=True,claude_only=True,fault='drop-project')
                self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                other=next(e for e in before['plugins'][PLUGIN] if e['projectPath']!=work)
                self.assertIn(other,after['plugins'][PLUGIN])
                self.assertEqual(receipt["hosts"]["claude"]["projectPath"],work)
                self.assertEqual(receipt["hosts"]["claude"]["scope"],scope)

    def test_other_scope_does_not_satisfy_requested_user_install(self):
        proc,before,after,calls,receipt,_,_=self.run_case(only_other_scope=True,claude_only=True)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        self.assertEqual(len(calls),1)
        self.assertTrue(any(e['scope']=='user' for e in after['plugins'][PLUGIN]))
        self.assertIn(before['plugins'][PLUGIN][0],after['plugins'][PLUGIN])
        self.assertTrue(receipt)

    def test_wrong_scope_after_native_call_cannot_write_success_receipt(self):
        proc,_,after,_,receipt,_,_=self.run_case(claude_only=True,fault='wrong-user')
        self.assertNotEqual(proc.returncode,0)
        self.assertFalse(any(e['scope']=='user' for e in after['plugins'][PLUGIN]))
        self.assertFalse(receipt)



class InstallationIdentityUnitTests(unittest.TestCase):
    def test_codex_hashes_the_cache_not_the_marketplace_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile=Path(tmp)/'profile'
            cache=profile/'plugins/cache/agent-tooling/target/1.0.0'
            cache.mkdir(parents=True)
            checkout=Path(tmp)/'marketplace/plugins/target';checkout.mkdir(parents=True)
            replies=[{'marketplaces':[{'name':'agent-tooling','source':'DevGuyRash/agent-tooling'}]}, {'installed':[{'pluginId':PLUGIN,'version':'1.0.0','source':{'source':'local','path':str(checkout)}}]}]
            with mock.patch('scripts.install_all.run_json',side_effect=replies):
                state=discover('codex','codex',{'CODEX_HOME':str(profile)})
            self.assertEqual(state.installed[PLUGIN].root,cache)
            self.assertNotEqual(state.installed[PLUGIN].root,checkout)

    def test_receipts_do_not_transfer_identity_between_projects(self):
        receipt={'hosts':{'claude':{'scope':'project','projectPath':'/fixture/a','plugins':{PLUGIN:{'version':'1.0.0','digest':'a'*64}}}}}
        self.assertIsNone(receipt_identity(receipt,'claude',PLUGIN,scope='project',project_path=Path('/fixture/b')))
        self.assertIsNone(receipt_identity(receipt,'claude',PLUGIN,scope='user'))
        self.assertIsNotNone(receipt_identity(receipt,'claude',PLUGIN,scope='project',project_path=Path('/fixture/a')))

if __name__=='__main__':unittest.main()
