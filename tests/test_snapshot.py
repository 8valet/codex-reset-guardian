import unittest

class SnapshotTests(unittest.TestCase):
    def test_current_multi_bucket_and_credit_sort(self):
        from codex_reset_guardian.snapshot import usage_windows, available_credits
        snap={'rateLimitsByLimitId':{'codex':{
          'primary':{'windowDurationMins':300,'usedPercent':20,'resetsAt':100},
          'secondary':{'windowDurationMins':10080,'usedPercent':5,'resetsAt':200}}},
          'rateLimitResetCredits':{'availableCount':2,'credits':[
            {'id':'later','status':'available','expiresAt':500},
            {'id':'first','status':'available','expiresAt':400},
            {'id':'used','status':'used','expiresAt':300}]}}
        windows=usage_windows(snap)
        self.assertEqual([(w.name,w.remaining_percent) for w in windows],[('5-hour',80),('weekly',95)])
        count,credits=available_credits(snap)
        self.assertEqual(count,2)
        self.assertEqual([c['id'] for c in credits],['first','later'])

    def test_legacy_rate_limits_fallback(self):
        from codex_reset_guardian.snapshot import usage_windows
        snap={'rateLimits':{'primary':{'windowDurationMins':300,'usedPercent':91},'secondary':{'windowDurationMins':10080,'usedPercent':17}}}
        self.assertEqual([w.remaining_percent for w in usage_windows(snap)],[9,83])

    def test_missing_credit_details_never_invents_credit(self):
        from codex_reset_guardian.snapshot import available_credits
        count,credits=available_credits({'rateLimitResetCredits':{'availableCount':2,'credits':None}})
        self.assertEqual(count,2); self.assertEqual(credits,[])

class SnapshotSafetyTests(unittest.TestCase):
    def test_credit_without_id_is_not_schedulable(self):
        from codex_reset_guardian.snapshot import available_credits
        count,credits=available_credits({'rateLimitResetCredits':{'availableCount':1,'credits':[{'status':'available','expiresAt':123}]}})
        self.assertEqual(count,1); self.assertEqual(credits,[])

class FractionalUsageTests(unittest.TestCase):
    def test_fractional_used_percent_preserves_eligibility_threshold(self):
        from codex_reset_guardian.snapshot import usage_windows
        from codex_reset_guardian.policy import eligibility
        snap={'rateLimits':{'primary':{'windowDurationMins':300,'usedPercent':20.1}}}
        windows=usage_windows(snap)
        self.assertAlmostEqual(windows[0].remaining_percent,79.9)
        self.assertTrue(eligibility(windows))

class MalformedUsageTests(unittest.TestCase):
    def test_missing_or_non_numeric_usage_is_unknown_not_zero(self):
        from codex_reset_guardian.snapshot import usage_windows
        snap={'rateLimits':{'primary':{'windowDurationMins':300},'secondary':{'windowDurationMins':10080,'usedPercent':'bad'}}}
        self.assertEqual(usage_windows(snap),[])
