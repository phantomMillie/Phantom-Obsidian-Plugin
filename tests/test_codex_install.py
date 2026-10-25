import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugin/scripts'))
spec = importlib.util.spec_from_file_location('install_codex', ROOT / 'plugin/scripts/install_codex.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
spec = importlib.util.spec_from_file_location('skill_compat', ROOT / 'plugin/scripts/install_skill_compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


def framework(temp):
    root = pathlib.Path(temp) / 'framework space'
    vault = pathlib.Path(temp) / 'vault space'
    vault.mkdir()
    (vault / 'AGENTS.md').write_text('fixture vault rules')
    root.mkdir()
    (root / 'config.json').write_text(json.dumps({'vault': str(vault)}))
    (root / 'MILLIE.template.md').write_text('Vault: {{VAULT}}')
    scripts = root / 'plugin/scripts'
    scripts.mkdir(parents=True)
    (scripts / 'project_lint.py').write_text('import json;print(json.dumps([{"project":"Sample","missing":["due"]}]))')
    skill = root / 'plugin/skills/example'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: example\ndescription: fixture\n---\n')
    (skill / 'resource.txt').write_text('adjacent resource')
    return root, vault


class CodexInstallTests(unittest.TestCase):
    def test_fresh_codex_only_install_repeat_and_preserve_foreign_hooks(self):
        with tempfile.TemporaryDirectory(prefix='install space ') as temp:
            root, vault = framework(temp)
            home = pathlib.Path(temp) / 'home'
            path = home / '.codex/hooks.json'
            path.parent.mkdir(parents=True)
            foreign = {'hooks': [{'type': 'command', 'command': 'echo kept'}]}
            path.write_text(json.dumps({'hooks': {'SessionStart': [foreign]}}))
            agents = home / '.codex/AGENTS.md'
            agents.write_text('Existing user instructions\n')
            installer.install(home, root)
            before = path.read_bytes(), agents.read_bytes()
            installer.install(home, root)
            self.assertEqual(before, (path.read_bytes(), agents.read_bytes()))
            self.assertEqual(json.loads(path.read_text())['hooks']['SessionStart'][0], foreign)
            self.assertIn('Existing user instructions', agents.read_text())
            self.assertEqual(agents.read_text().count(installer.START), 1)
            self.assertIn(str(vault), agents.read_text())
            self.assertEqual((home / '.agents/skills/example/resource.txt').read_text(), 'adjacent resource')
            self.assertFalse((home / '.codex/config.toml').exists())
            self.assertEqual(list(vault.iterdir()), [vault / 'AGENTS.md'])

    def test_symlink_unavailable_copies_complete_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = framework(temp)
            home = pathlib.Path(temp) / 'home'
            with mock.patch.object(pathlib.Path, 'symlink_to', side_effect=OSError('Windows symlink privilege absent')):
                installer.install(home, root)
            self.assertEqual((home / '.agents/skills/example/resource.txt').read_text(), 'adjacent resource')

    def test_remove_leaves_foreign_hooks_and_vault(self):
        with tempfile.TemporaryDirectory() as temp:
            root, vault = framework(temp)
            home = pathlib.Path(temp) / 'home'
            installer.install(home, root)
            path = home / '.codex/hooks.json'
            data = json.loads(path.read_text())
            data['hooks']['SessionStart'].append({'hooks': [{'command': 'echo foreign'}]})
            path.write_text(json.dumps(data))
            installer.install(home, root, remove=True)
            self.assertEqual(json.loads(path.read_text())['hooks']['SessionStart'][-1]['hooks'][0]['command'], 'echo foreign')
            self.assertTrue((vault / 'AGENTS.md').exists())

    def test_readonly_json_hook_no_bootstrap_or_state_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root, vault = framework(temp)
            env = dict(os.environ, MILLIE_HOME=str(root), PYTHONDONTWRITEBYTECODE='1')
            before = {str(p): p.read_bytes() for p in pathlib.Path(temp).rglob('*') if p.is_file()}
            for event, prompt, active in [('SessionStart', '', True), ('UserPromptSubmit', 'Sample 작업', True), ('UserPromptSubmit', 'unrelated', False)]:
                result = subprocess.run([sys.executable, str(ROOT / 'plugin/hooks/codex_guard.py')], input=json.dumps({'hook_event_name': event, 'prompt': prompt}), text=True, capture_output=True, env=env, check=True)
                data = json.loads(result.stdout)
                self.assertEqual(bool(data), active)
                if active:
                    self.assertEqual(data['hookSpecificOutput']['hookEventName'], event)
            self.assertEqual(before, {str(p): p.read_bytes() for p in pathlib.Path(temp).rglob('*') if p.is_file()})

    def test_readonly_profile_refused_before_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = framework(temp)
            home = pathlib.Path(temp) / 'home'
            config = home / '.codex/config.toml'
            config.parent.mkdir(parents=True)
            config.write_text('sandbox_mode="read-only"\n')
            with self.assertRaises(ValueError):
                installer.install(home, root, permissions=True)
            self.assertFalse((home / '.codex/hooks.json').exists())
            self.assertFalse((home / '.agents').exists())


class ExternalSkillTests(unittest.TestCase):
    def test_source_resources_copy_idempotence_and_user_edit_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = framework(temp)
            home = pathlib.Path(temp) / 'home'
            source = pathlib.Path(temp) / 'upstream'
            skill = source / 'skills/caveman-explore'
            skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text('---\nname: caveman-explore\ndescription: fixture\ntools: Read, Glob\nmodel: haiku\n---\nFind code.\n')
            (skill / 'extra.md').write_text('preserved resource')
            (home / '.gemini').mkdir(parents=True)
            compat.install(home, root, source)
            target = home / '.agents/skills/caveman-explore/SKILL.md'
            gemini_target = home / '.gemini/config/skills/caveman-explore/SKILL.md'
            self.assertTrue(gemini_target.exists())
            gemini_skills_json = json.loads((home / '.gemini/config/skills.json').read_text())
            self.assertTrue(any(pathlib.Path(e.get('path')).resolve() == (home / '.agents/skills').resolve() for e in gemini_skills_json.get('entries', [])))
            before = target.read_bytes()
            compat.install(home, root, source)
            self.assertEqual(before, target.read_bytes())
            self.assertNotIn('model: haiku', target.read_text())
            self.assertEqual((target.parent / 'extra.md').read_text(), 'preserved resource')
            target.write_text('independent user edit')
            with self.assertRaises(ValueError):
                compat.install(home, root, source)
            self.assertEqual(target.read_text(), 'independent user edit')

    def test_existing_unmanaged_caveman_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root, _ = framework(temp)
            home = pathlib.Path(temp) / 'home'
            source = pathlib.Path(temp) / 'upstream/skills/caveman'
            source.mkdir(parents=True)
            (source / 'SKILL.md').write_text('upstream')
            target = home / '.agents/skills/caveman/SKILL.md'
            target.parent.mkdir(parents=True)
            target.write_text('my existing skill')
            compat.install(home, root, source.parents[1])
            self.assertEqual(target.read_text(), 'my existing skill')

    def test_stats_never_falls_back_to_wrong_session(self):
        with tempfile.TemporaryDirectory() as temp:
            home = pathlib.Path(temp)
            sessions = home / 'sessions'
            sessions.mkdir()
            for name, tokens in [('a', 12), ('b', 900)]:
                (sessions / ('rollout-' + name + '.jsonl')).write_text(json.dumps({'type': 'session_meta', 'payload': {'id': name}}) + '\n' + json.dumps({'payload': {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': tokens}}}}) + '\n')
            env = dict(os.environ, CODEX_HOME=str(home), CODEX_THREAD_ID='a')
            result = subprocess.run([sys.executable, str(ROOT / 'plugin/scripts/codex_stats.py')], env=env, text=True, capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout)['measured_token_usage']['input_tokens'], 12)
            result = subprocess.run([sys.executable, str(ROOT / 'plugin/scripts/codex_stats.py'), '--thread', 'missing'], env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
