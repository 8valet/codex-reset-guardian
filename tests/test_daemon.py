import tempfile, unittest
from pathlib import Path

class Capture:
    def __init__(self): self.events=[]
    def send(self,event): self.events.append(event); return [('capture',True,None)]

class RPC:
    def __init__(self,seen,outcome='reset'): self.seen=seen; self.outcome=outcome
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def request(self,method,params=None,timeout=30):
        if method=='account/rateLimits/read':
            return {'accountId':'acct','rateLimitResetCredits':{'availableCount':1,'credits':[{'id':'c1','status':'available','expiresAt':999999}]}}
        self.seen.append(params); return {'outcome':self.outcome}

class SlotPolicyTests(unittest.TestCase):
    def test_custom_redeem_target_never_schedules_earlier_fallback(self):
        from codex_reset_guardian.daemon import slots_for
        self.assertEqual(slots_for(90),[90,60,30])
        self.assertEqual(slots_for(45),[45,30])
        self.assertEqual(slots_for(30),[30])

class DaemonTests(unittest.TestCase):
    def cfg(self):
        return {'guardian':{'redeem_before_seconds':90,'preflight_before_seconds':300,'network_retry_seconds':10,'poll_far_seconds':1800,'poll_day_seconds':600,'poll_hour_seconds':120,'poll_ten_min_seconds':30},'reminders':{'enabled':True,'checkpoints_seconds':[86400,21600,5400,900]}}
    def snapshot(self,expires,used5=10,usedw=5):
        return {'accountId':'acct','rateLimitsByLimitId':{'codex':{'primary':{'windowDurationMins':300,'usedPercent':used5},'secondary':{'windowDurationMins':10080,'usedPercent':usedw}}},'rateLimitResetCredits':{'availableCount':1,'credits':[{'id':'c1','status':'available','title':'Full reset','expiresAt':expires}]}}
    def test_checkpoint_is_deduped_and_mute_suppresses_future(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.daemon import GuardianDaemon
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); cap=Capture(); now=100000
            d=GuardianDaemon(store,self.cfg(),lambda:self.snapshot(now+20000),lambda:None,cap,clock=lambda:now)
            d.tick(); d.tick()
            self.assertEqual(len(cap.events),1); self.assertEqual(cap.events[0]['title'],'Banked reset expires in 6 hours')
            store.set_muted('c1',True); now2=now+15000
            d.clock=lambda:now2; d.read_limits=lambda:self.snapshot(now+5000)
            d.tick(); self.assertEqual(len(cap.events),1)
            store.close()
    def test_disarmed_never_consumes_and_armed_does(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.daemon import GuardianDaemon
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); seen=[]; now=100000
            factory=lambda:RPC(seen)
            d=GuardianDaemon(store,self.cfg(),lambda:self.snapshot(now+80,used5=90),factory,Capture(),clock=lambda:now)
            d.tick(); self.assertEqual(seen,[])
            store.set_armed(True); d.tick(); self.assertEqual(len(seen),1)
            store.close()
    def test_uncertain_redemption_uses_network_retry_interval(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.daemon import GuardianDaemon
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); seen=[]; now=100000
            store.pin_account('acct'); store.set_armed(True)
            d=GuardianDaemon(store,self.cfg(),lambda:self.snapshot(now+80,used5=90),lambda:RPC(seen,'futureOutcome'),Capture(),clock=lambda:now)
            self.assertEqual(d.tick(),10)
            store.close()

    def test_success_outcome_blocks_second_consume_while_credit_lingers(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.daemon import GuardianDaemon
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); seen=[]; now=100000; store.pin_account('acct'); store.set_armed(True)
            row=store.create_attempt('c1',90); store.update_attempt('c1',90,outcome='reset')
            d=GuardianDaemon(store,self.cfg(),lambda:self.snapshot(now+50,used5=90),lambda:RPC(seen),Capture(),clock=lambda:now)
            d.tick(); self.assertEqual(seen,[])
            store.close()
    def test_notification_failure_does_not_dedupe_and_retries_after_recovery(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.daemon import GuardianDaemon
        class Flaky:
            def __init__(self): self.calls=0
            def send(self,event):
                self.calls+=1
                return [('push',self.calls>1,None if self.calls>1 else 'offline')]
        with tempfile.TemporaryDirectory() as td:
            now=100000; store=Store(Path(td)/'g.db'); flaky=Flaky()
            d=GuardianDaemon(store,self.cfg(),lambda:self.snapshot(now+20000),lambda:None,flaky,clock=lambda:now)
            d.tick(); self.assertFalse(store.event_was_sent('codex.banked-reminder:c1:21600'))
            self.assertEqual(len(store.pending_notifications()),1)
            d.tick(); self.assertTrue(store.event_was_sent('codex.banked-reminder:c1:21600'))
            self.assertEqual(store.pending_notifications(),[])
            self.assertEqual(flaky.calls,2)
            store.close()

class PartialDetailSafetyTests(unittest.TestCase):
    def test_partial_credit_details_do_not_finalize_previous_reset(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.daemon import GuardianDaemon
        cfg={'guardian':{'redeem_before_seconds':90,'preflight_before_seconds':300,'network_retry_seconds':10,'poll_far_seconds':1800,'poll_day_seconds':600,'poll_hour_seconds':120,'poll_ten_min_seconds':30},'reminders':{'enabled':True,'checkpoints_seconds':[86400,21600,5400,900]}}
        now=100000; cap=Capture()
        full={'accountId':'acct','rateLimits':{},'rateLimitResetCredits':{'availableCount':1,'credits':[{'id':'c1','status':'available','expiresAt':200000}]}}
        partial={'accountId':'acct','rateLimits':{},'rateLimitResetCredits':{'availableCount':1,'credits':None}}
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); current=[full]
            d=GuardianDaemon(store,cfg,lambda:current[0],lambda:None,cap,clock=lambda:now)
            d.tick(); current[0]=partial; d.tick()
            self.assertFalse(any(e.get('state')=='gone' for e in cap.events))
            self.assertIn('c1',store.get_meta('last_credit_json'))
            store.close()

class TerminalNotificationRetryTests(unittest.TestCase):
    def test_failed_terminal_delivery_is_retried_after_current_credit_changes(self):
        from codex_reset_guardian.store import Store
        from codex_reset_guardian.daemon import GuardianDaemon
        cfg={'guardian':{'redeem_before_seconds':90,'preflight_before_seconds':300,'network_retry_seconds':10,'poll_far_seconds':1800,'poll_day_seconds':600,'poll_hour_seconds':120,'poll_ten_min_seconds':30},'reminders':{'enabled':True,'checkpoints_seconds':[86400,21600,5400,900]}}
        now=100000
        first={'accountId':'acct','rateLimits':{},'rateLimitResetCredits':{'availableCount':1,'credits':[{'id':'c1','status':'available','expiresAt':200000}]}}
        second={'accountId':'acct','rateLimits':{},'rateLimitResetCredits':{'availableCount':1,'credits':[{'id':'c2','status':'available','expiresAt':300000}]}}
        class Flaky:
            def __init__(self): self.calls=0; self.titles=[]
            def send(self,event):
                self.calls+=1; self.titles.append(event['title'])
                return [('push',self.calls>1,None if self.calls>1 else 'offline')]
        with tempfile.TemporaryDirectory() as td:
            store=Store(Path(td)/'g.db'); current=[first]; flaky=Flaky()
            d=GuardianDaemon(store,cfg,lambda:current[0],lambda:None,flaky,clock=lambda:now)
            d.tick(); current[0]=second; d.tick()
            self.assertEqual(len(store.pending_notifications()),1)
            d.tick()
            self.assertEqual(store.pending_notifications(),[])
            self.assertIn('Banked reset no longer available',flaky.titles)
            store.close()
