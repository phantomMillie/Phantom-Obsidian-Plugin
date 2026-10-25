import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('permissions', ROOT / 'plugin/scripts/codex_permissions.py')
permissions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(permissions)


@unittest.skipUnless(importlib.util.find_spec('tomllib'), 'optional permission merge needs Python 3.11+')
class PermissionTests(unittest.TestCase):
    def test_merge_multiline_preserve_mode_approval_network_and_idempotence(self):
        with tempfile.TemporaryDirectory(prefix='home space ') as temp:
            home = pathlib.Path(temp)
            path = home / '.codex/config.toml'
            path.parent.mkdir()
            path.write_text('model = "kept"\napproval_policy = "never"\n[sandbox_workspace_write]\nnetwork_access = false\nwritable_roots = [\n "/existing", # kept\n]\n[projects."/work"]\ntrust_level="trusted"\n')
            self.assertTrue(permissions.configure(home, [home / '.ai-criteria']))
            text = path.read_text()
            self.assertIn('approval_policy = "never"', text)
            self.assertIn('network_access = false', text)
            self.assertIn('trust_level="trusted"', text)
            self.assertIn('/existing', text)
            self.assertFalse(permissions.configure(home, [home / '.ai-criteria']))
            self.assertEqual(text, path.read_text())

    def test_new_config_has_only_explicit_data_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            home = pathlib.Path(temp)
            permissions.configure(home, [home / 'data'])
            text = (home / '.codex/config.toml').read_text()
            self.assertNotIn('approval_policy', text)
            self.assertNotIn('danger-full-access', text)
            self.assertIn(str(home / 'data'), text)

    def test_named_profiles_and_readonly_are_not_silently_replaced(self):
        for text in ['default_permissions="custom"\n', 'sandbox_mode="read-only"\n']:
            with self.subTest(text=text), tempfile.TemporaryDirectory() as temp:
                home = pathlib.Path(temp)
                path = home / '.codex/config.toml'
                path.parent.mkdir()
                path.write_text(text)
                with self.assertRaises(ValueError):
                    permissions.configure(home, [home / 'data'])
                self.assertEqual(text, path.read_text())


    def test_symlink_config_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            home = pathlib.Path(temp)
            source = home / 'dotfile.toml'
            source.write_text('model="kept"\n')
            path = home / '.codex/config.toml'
            path.parent.mkdir()
            try:
                path.symlink_to(source)
            except OSError:
                self.skipTest('symlink unavailable')
            with self.assertRaises(ValueError):
                permissions.configure(home, [home / 'data'])
            self.assertTrue(path.is_symlink())
            self.assertEqual(source.read_text(), 'model="kept"\n')
