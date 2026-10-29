import tempfile, unittest
from pathlib import Path

class FakeRPC:
    def __init__(self, outcomes, seen): self.outcomes=outcomes; self.seen=seen
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def request(self, method, params, timeout=30):
        self.seen.append(dict(params))
        item=self.outcomes.pop(0)
        if isinstance(item,Exception): raise item
        return {'outcome':item}

class RedemptionTests(unittest.TestCase):
    def test_uncertain_retry_reuses_same_idempotency_key(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.redemption import attempt_redeem
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); seen=[]; outcomes=[TimeoutError('lost'), 'reset']
            factory=lambda: FakeRPC(outcomes,seen)
            self.assertEqual(attempt_redeem(store,factory,'c1',90),'uncertain')
            self.assertEqual(attempt_redeem(store,factory,'c1',60),'reset')
            self.assertEqual(seen[0]['idempotencyKey'],seen[1]['idempotencyKey'])
            self.assertEqual(seen[0]['creditId'],'c1')
            store.close()

    def test_explicit_nothing_to_reset_finishes_that_slot(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.redemption import attempt_redeem
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); seen=[]; outcomes=['nothingToReset','reset']
            factory=lambda: FakeRPC(outcomes,seen)
            self.assertEqual(attempt_redeem(store,factory,'c1',90),'nothingToReset')
            self.assertEqual(attempt_redeem(store,factory,'c1',60),'reset')
            self.assertNotEqual(seen[0]['idempotencyKey'],seen[1]['idempotencyKey'])
            store.close()

    def test_unknown_outcome_fails_closed_as_uncertain(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.redemption import attempt_redeem
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); seen=[]; outcomes=['futureOutcome']
            self.assertEqual(attempt_redeem(store,lambda:FakeRPC(outcomes,seen),'c1',90),'uncertain')
            self.assertIsNone(store.pending_attempt('c1')['outcome'])
            store.close()

class VerifyingRPC:
    def __init__(self,snapshot,seen,outcome='reset'): self.snapshot=snapshot; self.seen=seen; self.outcome=outcome
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def request(self,method,params=None,timeout=30):
        self.seen.append((method,params))
        if method=='account/rateLimits/read': return self.snapshot
        if method=='account/rateLimitResetCredit/consume': return {'outcome':self.outcome}
        raise AssertionError(method)

class RedemptionPreconsumeVerificationTests(unittest.TestCase):
    def snapshot(self,account='acct',credits=None,count=None):
        if credits is None: credits=[{'id':'c1','status':'available','expiresAt':999}]
        return {'accountId':account,'rateLimitResetCredits':{'availableCount':len(credits) if count is None else count,'credits':credits}}

    def test_same_connection_reverifies_account_and_exact_credit_before_consume(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.redemption import attempt_redeem
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); store.pin_account('acct'); store.set_armed(True); seen=[]
            out=attempt_redeem(store,lambda:VerifyingRPC(self.snapshot(),seen),'c1',90,expected_account_id='acct')
            self.assertEqual(out,'reset')
            self.assertEqual([m for m,_ in seen],['account/rateLimits/read','account/rateLimitResetCredit/consume'])
            store.close()

    def test_account_change_disarms_and_never_consumes(self):
        from codex_reset_guardian.store import Store, AccountChanged
        from codex_reset_guardian.redemption import attempt_redeem
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); store.pin_account('acct'); store.set_armed(True); seen=[]
            with self.assertRaises(AccountChanged):
                attempt_redeem(store,lambda:VerifyingRPC(self.snapshot(account='other'),seen),'c1',90,expected_account_id='acct')
            self.assertFalse(store.is_armed())
            self.assertEqual([m for m,_ in seen],['account/rateLimits/read'])
            self.assertIsNone(store.pending_attempt('c1'))
            store.close()

    def test_missing_or_partial_target_details_never_consume(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.redemption import attempt_redeem
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); store.pin_account('acct')
            for snap,expected in [(self.snapshot(credits=[],count=0),'targetMissing'),({'accountId':'acct','rateLimitResetCredits':{'availableCount':1,'credits':None}},'detailsUnavailable')]:
                seen=[]
                self.assertEqual(attempt_redeem(store,lambda s=snap:VerifyingRPC(s,seen),'c1',90,expected_account_id='acct'),expected)
                self.assertEqual([m for m,_ in seen],['account/rateLimits/read'])
                self.assertIsNone(store.pending_attempt('c1'))
            store.close()

    def test_capped_details_can_redeem_when_exact_target_is_present(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.redemption import attempt_redeem
        snap=self.snapshot(credits=[{'id':'c1','status':'available','expiresAt':999}],count=2)
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); store.pin_account('acct'); store.set_armed(True); seen=[]
            self.assertEqual(attempt_redeem(store,lambda:VerifyingRPC(snap,seen),'c1',90,expected_account_id='acct'),'reset')
            self.assertEqual([m for m,_ in seen],['account/rateLimits/read','account/rateLimitResetCredit/consume'])
            store.close()
