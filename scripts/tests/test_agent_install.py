from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import agent_install


class AgentInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'codex'

    def test_install_is_owned_idempotent_and_updates_only_selected_plugin(self):
        desired = {'reviewer.toml': 'name = "example:reviewer"\n'}
        plan = agent_install.plan(self.home, 'example@market', desired)
        agent_install.apply(plan)
        path = next((self.home / 'agents').glob('*.toml'))
        self.assertEqual(path.read_text(), desired['reviewer.toml'])
        self.assertEqual(agent_install.plan(self.home, 'example@market', desired).changes, {})
        agent_install.apply(agent_install.plan(self.home, 'other@market', {'helper.toml': 'name = "other:helper"\n'}))
        agent_install.apply(agent_install.plan(self.home, 'example@market', {}))
        self.assertFalse(path.exists())
        self.assertEqual(len(list((self.home / 'agents').glob('*.toml'))), 1)

    def test_user_modified_agent_blocks_replacement(self):
        agent_install.apply(agent_install.plan(self.home, 'example@market', {'reviewer.toml': 'name = "example:reviewer"\n'}))
        path = next((self.home / 'agents').glob('*.toml'))
        path.write_text('name = "my-edited-agent"\n')
        with self.assertRaisesRegex(agent_install.AgentInstallError, 'modified'):
            agent_install.plan(self.home, 'example@market', {})
        self.assertEqual(path.read_text(), 'name = "my-edited-agent"\n')

    def test_same_named_user_agent_blocks_before_writes(self):
        root = self.home / 'agents'
        root.mkdir(parents=True)
        (root / 'user.toml').write_text('name = "example:reviewer"\n')
        with self.assertRaisesRegex(agent_install.AgentInstallError, 'name.*already'):
            agent_install.plan(self.home, 'example@market', {'reviewer.toml': 'name = "example:reviewer"\n'})
        self.assertEqual(list(root.iterdir()), [root / 'user.toml'])

    def test_symlinked_receipt_and_agent_are_rejected(self):
        root = self.home / 'agents'
        root.mkdir(parents=True)
        external = Path(self.temp.name) / 'external'
        external.write_text('{}')
        (root / '.plugin-portability.json').symlink_to(external)
        with self.assertRaises(agent_install.AgentInstallError):
            agent_install.plan(self.home, 'example@market', {})
        self.assertEqual(external.read_text(), '{}')

    def test_symlinked_user_agents_are_read_never_refused_or_touched(self):
        # Dotfile managers link a user's own agents into CODEX_HOME/agents; projection must read them, not refuse.
        root = self.home / 'agents'
        root.mkdir(parents=True)
        dotfiles = Path(self.temp.name) / 'dotfiles'
        dotfiles.mkdir()
        (dotfiles / 'auditor.toml').write_text('name = "auditor"\ndescription = "Mine."\ndeveloper_instructions = "Audit."\n')
        (root / 'auditor.toml').symlink_to(dotfiles / 'auditor.toml')
        (root / 'gone.toml').symlink_to(dotfiles / 'missing.toml')
        self.assertEqual(agent_install.plan(self.home, 'example@market', {}).changes, {})
        agent_install.apply(agent_install.plan(self.home, 'example@market', {'reviewer.toml': 'name = "example:reviewer"\n'}))
        self.assertTrue((root / 'auditor.toml').is_symlink())
        self.assertEqual((dotfiles / 'auditor.toml').read_text(), 'name = "auditor"\ndescription = "Mine."\ndeveloper_instructions = "Audit."\n')
        with self.assertRaisesRegex(agent_install.AgentInstallError, 'name.*already'):
            agent_install.plan(self.home, 'other@market', {'auditor.toml': 'name = "auditor"\n'})

    def test_a_linked_agents_directory_is_left_alone_only_when_there_is_nothing_to_do(self):
        # A dotfile manager may move the agents directory, receipt and all, and link it back. With nothing to project
        # for an owner and nothing recorded for it, the planner leaves the link alone; an owner whose recorded agents
        # must go (its plugin was disabled) is refused like any write through the link, never silently skipped.
        owner, other = 'example@market', 'other@market'
        agent_install.apply(agent_install.plan(self.home, owner, {'reviewer.toml': 'name = "example:reviewer"\n'}))
        moved = Path(self.temp.name) / 'dotfiles-agents'
        (self.home / 'agents').rename(moved)
        (self.home / 'agents').symlink_to(moved)
        self.assertEqual({}, agent_install.plan_many(self.home, {other: {}}).changes)
        with self.assertRaisesRegex(agent_install.AgentInstallError, 'symlink'):
            agent_install.plan_many(self.home, {owner: {}})
        self.assertEqual(1, len(list(moved.glob('plugin-port-*.toml'))))
        (moved / agent_install.RECEIPT).write_text('not json')
        with self.assertRaisesRegex(agent_install.AgentInstallError, 'symlink'):
            agent_install.plan_many(self.home, {other: {}})

    def test_malformed_user_agent_does_not_block_projection(self):
        # Codex ignores a malformed role file with a warning, so it cannot collide and must not stop installation.
        root = self.home / 'agents'
        root.mkdir(parents=True)
        (root / 'broken.toml').write_text('name = [unclosed\n')
        (root / 'nameless.toml').write_text('description = "No name."\n')
        agent_install.apply(agent_install.plan(self.home, 'example@market', {'reviewer.toml': 'name = "example:reviewer"\n'}))
        self.assertEqual((root / 'broken.toml').read_text(), 'name = [unclosed\n')
        self.assertEqual(len(list(root.glob('plugin-port-*.toml'))), 1)

    def test_symlinked_owned_agent_is_rejected(self):
        agent_install.apply(agent_install.plan(self.home, 'example@market', {'reviewer.toml': 'name = "example:reviewer"\n'}))
        owned = next((self.home / 'agents').glob('plugin-port-*.toml'))
        external = Path(self.temp.name) / 'external.toml'
        external.write_text(owned.read_text())
        owned.unlink()
        owned.symlink_to(external)
        with self.assertRaises(agent_install.AgentInstallError):
            agent_install.plan(self.home, 'example@market', {})

    def test_failure_rolls_back_agent_files_and_receipt(self):
        original = {'reviewer.toml': 'name = "example:reviewer"\n'}
        agent_install.apply(agent_install.plan(self.home, 'example@market', original))
        before = {p.name: p.read_bytes() for p in (self.home / 'agents').iterdir() if p.is_file()}
        plan = agent_install.plan(self.home, 'example@market', {'helper.toml': 'name = "example:helper"\n'})
        real_replace = agent_install.os.replace
        def fail_receipt(source, destination):
            if Path(destination).name == '.plugin-portability.json':
                raise OSError('injected receipt failure')
            return real_replace(source, destination)
        with patch.object(agent_install.os, 'replace', side_effect=fail_receipt):
            with self.assertRaisesRegex(OSError, 'injected'):
                agent_install.apply(plan)
        after = {p.name: p.read_bytes() for p in (self.home / 'agents').iterdir() if p.is_file()}
        self.assertEqual(before, after)

    def test_stale_plan_refuses_concurrent_user_change(self):
        plan = agent_install.plan(self.home, 'example@market', {'reviewer.toml': 'name = "example:reviewer"\n'})
        agent_install.apply(plan)
        with self.assertRaisesRegex(agent_install.AgentInstallError, 'changed since'):
            agent_install.apply(plan)

    def test_multiple_plugins_preflight_as_one_transaction(self):
        owners = {
            'one@market': {'review.toml': 'name = "one:review"\n'},
            'two@market': {'review.toml': 'name = "two:review"\n'},
        }
        agent_install.apply(agent_install.plan_many(self.home, owners))
        self.assertEqual(len(list((self.home / 'agents').glob('*.toml'))), 2)
        self.assertEqual(agent_install.plan_many(self.home, owners).changes, {})
        owners['two@market']['review.toml'] = 'name = "one:review"\n'
        with self.assertRaisesRegex(agent_install.AgentInstallError, 'name.*already'):
            agent_install.plan_many(self.home, owners)

    def test_legacy_configured_agent_name_is_not_shadowed(self):
        self.home.mkdir()
        (self.home / 'config.toml').write_text('[agents."example:reviewer"]\ndescription = "My agent"\nconfig_file = "review.toml"\n')
        with self.assertRaisesRegex(agent_install.AgentInstallError, 'name.*already'):
            agent_install.plan(self.home, 'example@market', {'review.toml': 'name = "example:reviewer"\n'})
        self.assertFalse((self.home / 'agents').exists())
