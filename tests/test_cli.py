import unittest
class CliTests(unittest.TestCase):
    def test_parser_exposes_public_commands(self):
        from codex_reset_guardian.cli import build_parser
        p=build_parser()
        for args,cmd in [(['status'],'status'),(['arm'],'arm'),(['disarm'],'disarm'),(['mute','c1'],'mute'),(['unmute','c1'],'unmute'),(['notify-test'],'notify-test'),(['run'],'run')]:
            self.assertEqual(p.parse_args(args).command,cmd)

class CliOfflineSafetyTests(unittest.TestCase):
    def test_disarm_does_not_require_live_codex(self):
        from unittest.mock import patch
        import codex_reset_guardian.cli as cli
        class Store:
            armed=True
            def set_armed(self,v): self.armed=v
        store=Store()
        with patch.object(cli,'_runtime',return_value=({},store)), patch.object(cli,'_live',side_effect=AssertionError('must not read Codex')):
            self.assertEqual(cli.main(['disarm']),0)
        self.assertFalse(store.armed)

    def test_disarm_ignores_broken_notification_secret_configuration(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import codex_reset_guardian.cli as cli
        from codex_reset_guardian.config import Paths
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            config=root/'config.toml'
            config.write_text('[notifications.telegram]\nenabled = true\nbot_token = "env:GUARDIAN_TEST_MISSING_SECRET"\nchat_id = "1"\n')
            with patch.object(cli,'default_paths',return_value=Paths(config,root/'state')):
                self.assertEqual(cli.main(['--config',str(config),'disarm']),0)

    def test_notify_test_does_not_require_live_codex(self):
        from unittest.mock import patch
        import codex_reset_guardian.cli as cli
        class Notifier:
            def send(self,event): return [('desktop',True,None)]
        with patch.object(cli,'_runtime',return_value=({},object())), patch.object(cli,'build_manager',return_value=Notifier()), patch.object(cli,'_live',side_effect=AssertionError('must not read Codex')):
            self.assertEqual(cli.main(['notify-test']),0)

class CliRepinTests(unittest.TestCase):
    def test_repin_bypasses_old_account_pin_guard_and_disarms(self):
        from unittest.mock import patch
        import codex_reset_guardian.cli as cli
        class Store:
            def __init__(self): self.repin_id=None
            def repin(self,v): self.repin_id=v
        store=Store()
        snapshot={'accountId':'new-account','rateLimitResetCredits':{'availableCount':0,'credits':[]}}
        with patch.object(cli,'_runtime',return_value=({},store)), patch.object(cli,'read_limits',return_value=snapshot), patch.object(cli,'_live',side_effect=AssertionError('repin must bypass existing pin')):
            self.assertEqual(cli.main(['repin']),0)
        self.assertEqual(store.repin_id,'new-account')

class CliLogsTests(unittest.TestCase):
    def test_logs_is_offline_and_accepts_limit(self):
        from unittest.mock import patch
        import codex_reset_guardian.cli as cli
        class Store:
            def recent_events(self,n):
                self.n=n
                return [{'ts':1700000000,'level':'WARN','event':'notification-failed','details':'offline'}]
        store=Store()
        with patch.object(cli,'_runtime',return_value=({},store)), patch.object(cli,'_live',side_effect=AssertionError('logs must be offline')):
            self.assertEqual(cli.main(['logs','-n','7']),0)
        self.assertEqual(store.n,7)
