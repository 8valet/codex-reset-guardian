import tempfile, unittest
from pathlib import Path

class ConfigTests(unittest.TestCase):
    def test_defaults_and_validation(self):
        from codex_reset_guardian.config import load_config
        cfg=load_config(Path('/definitely/missing/config.toml'))
        self.assertEqual(cfg['guardian']['redeem_before_seconds'],90)
        self.assertEqual(cfg['reminders']['checkpoints_seconds'],[86400,21600,5400,900])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.toml'; p.write_text('[guardian]\nredeem_before_seconds=20\n')
            with self.assertRaises(ValueError): load_config(p)
    def test_os_paths_are_user_scoped(self):
        from codex_reset_guardian.config import default_paths
        win=default_paths('windows',{'APPDATA':'C:/Users/A/AppData/Roaming','LOCALAPPDATA':'C:/Users/A/AppData/Local'},Path('C:/Users/A'))
        self.assertIn('codex-reset-guardian',str(win.config)); self.assertIn('codex-reset-guardian',str(win.state_dir))

class ReminderConfigTests(unittest.TestCase):
    def test_checkpoints_must_be_positive_unique_descending_values(self):
        from codex_reset_guardian.config import load_config
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.toml'; p.write_text('[reminders]\ncheckpoints_seconds=[86400,0,900]\n')
            with self.assertRaises(ValueError): load_config(p)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'ok.toml'; p.write_text('[reminders]\ncheckpoints_seconds=[900,86400,5400,900]\n')
            cfg=load_config(p)
            self.assertEqual(cfg['reminders']['checkpoints_seconds'],[86400,5400,900])
