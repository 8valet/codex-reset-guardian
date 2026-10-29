import tempfile, unittest
from pathlib import Path

class StoreTests(unittest.TestCase):
    def test_new_store_is_disarmed_and_account_change_disarms(self):
        from codex_reset_guardian.store import Store, AccountChanged
        with tempfile.TemporaryDirectory() as td, Store(Path(td)/'g.db') as s:
            self.assertFalse(s.is_armed())
            s.pin_account('acct-1'); s.set_armed(True)
            self.assertTrue(s.is_armed())
            with self.assertRaises(AccountChanged): s.pin_account('acct-2')
            self.assertFalse(s.is_armed())

    def test_credit_sync_and_per_credit_mute(self):
        from codex_reset_guardian.store import Store
        with tempfile.TemporaryDirectory() as td, Store(Path(td)/'g.db') as s:
            s.sync_credits([{'id':'c1','title':'Full reset','status':'available','expiresAt':123,'grantedAt':1}])
            self.assertEqual(s.current_credits()[0]['id'],'c1')
            self.assertFalse(s.is_muted('c1'))
            s.set_muted('c1',True); self.assertTrue(s.is_muted('c1'))
            s.set_muted('c1',False); self.assertFalse(s.is_muted('c1'))

class StoreLifecycleTests(unittest.TestCase):
    def test_context_manager_closes_connection(self):
        from codex_reset_guardian.store import Store
        import sqlite3
        with tempfile.TemporaryDirectory() as td:
            with Store(Path(td)/'g.db') as store:
                conn=store.db
                self.assertFalse(store.is_armed())
            with self.assertRaises(sqlite3.ProgrammingError): conn.execute('select 1')

class StorePrivacyAndLogsTests(unittest.TestCase):
    def test_recent_events_are_newest_first(self):
        from codex_reset_guardian.store import Store
        with tempfile.TemporaryDirectory() as td:
            with Store(Path(td)/'state'/'g.db') as store:
                store.log('INFO','first','one'); store.log('WARN','second','two')
                rows=store.recent_events(1)
                self.assertEqual(rows[0]['event'],'second')
                self.assertEqual(rows[0]['details'],'two')

    def test_posix_state_db_is_user_private(self):
        import os, stat
        if os.name == 'nt': self.skipTest('POSIX permissions do not apply on Windows')
        from codex_reset_guardian.store import Store
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'state'/'g.db'
            with Store(db): pass
            self.assertEqual(stat.S_IMODE(db.parent.stat().st_mode) & 0o077,0)
            self.assertEqual(stat.S_IMODE(db.stat().st_mode) & 0o077,0)
