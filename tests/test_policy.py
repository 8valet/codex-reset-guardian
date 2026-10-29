import unittest
from codex_reset_guardian.snapshot import UsageWindow

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.credit={'id':'c1','title':'Full reset','expiresAt':200000}
    def test_24h_heads_up_even_if_currently_eligible(self):
        from codex_reset_guardian.policy import reminder_event
        now=200000-80000
        prior={'remaining_seconds':90000,'eligibility':True}
        e=reminder_event(self.credit,[UsageWindow('5-hour',90,10),UsageWindow('weekly',10,90)],now,prior,False)
        self.assertEqual(e['kind'],'checkpoint'); self.assertEqual(e['checkpoint_seconds'],86400)
        self.assertIn('5-hour 10% left',e['message'])
    def test_later_checkpoint_is_quiet_while_eligible(self):
        from codex_reset_guardian.policy import reminder_event
        now=200000-20000; prior={'remaining_seconds':23000,'eligibility':True}
        self.assertIsNone(reminder_event(self.credit,[UsageWindow('5-hour',90,10),UsageWindow('weekly',10,90)],now,prior,False))
    def test_ineligible_to_eligible_emits_ready_once(self):
        from codex_reset_guardian.policy import reminder_event
        now=150000; windows=[UsageWindow('5-hour',21,79),UsageWindow('weekly',10,90)]
        e=reminder_event(self.credit,windows,now,{'remaining_seconds':51000,'eligibility':False},False)
        self.assertEqual(e['kind'],'ready'); self.assertIn('5-hour 79% left',e['message'])
        self.assertIsNone(reminder_event(self.credit,windows,now,{'remaining_seconds':50000,'eligibility':True},False))
    def test_natural_reset_can_warn_again_at_90m(self):
        from codex_reset_guardian.policy import reminder_event
        now=200000-5000
        e=reminder_event(self.credit,[UsageWindow('5-hour',10,90),UsageWindow('weekly',5,95)],now,{'remaining_seconds':6000,'eligibility':True},False)
        self.assertEqual(e['checkpoint_seconds'],5400); self.assertIn('More Codex usage',e['message'])
    def test_muted_suppresses_reminder_and_ready(self):
        from codex_reset_guardian.policy import reminder_event
        e=reminder_event(self.credit,[UsageWindow('5-hour',90,10)],120000,{'remaining_seconds':90000,'eligibility':False},True)
        self.assertIsNone(e)
    def test_terminal_is_credit_scoped_and_ignores_mute_concept(self):
        from codex_reset_guardian.policy import terminal_event
        previous={'id':'c1','expiresAt':100}
        attempts=[{'credit_id':'old','outcome':'reset'},{'credit_id':'c1','outcome':'reset'}]
        e=terminal_event(previous,None,attempts,50)
        self.assertEqual(e['state'],'redeemed'); self.assertEqual(e['dedupe_key'],'codex.banked-terminal:c1:redeemed')
        self.assertIsNone(terminal_event(previous,{'id':'c1'},attempts,50))

class PolicyConfigTests(unittest.TestCase):
    def test_custom_checkpoint_is_honored(self):
        from codex_reset_guardian.policy import reminder_event
        credit={'id':'c','expiresAt':10000}
        e=reminder_event(credit,[UsageWindow('weekly',10,90)],9200,{'remaining_seconds':1200,'eligibility':False},False,checkpoints=(1000,))
        self.assertEqual(e['checkpoint_seconds'],1000)

    def test_manual_disappearance_emits_gone_terminal(self):
        from codex_reset_guardian.policy import terminal_event
        e=terminal_event({'id':'c','expiresAt':10000},None,[],9000)
        self.assertEqual(e['state'],'gone'); self.assertEqual(e['title'],'Banked reset no longer available')

class UncertainTerminalTests(unittest.TestCase):
    def test_disappeared_credit_after_uncertain_attempt_reports_uncertain_terminal(self):
        from codex_reset_guardian.policy import terminal_event
        previous={'id':'c1','expiresAt':10000}
        attempts=[{'credit_id':'c1','outcome':None,'error':'timeout'}]
        e=terminal_event(previous,None,attempts,9000)
        self.assertEqual(e['state'],'uncertain')
        self.assertEqual(e['severity'],'warning')
        self.assertIn('uncertain',e['message'].lower())
