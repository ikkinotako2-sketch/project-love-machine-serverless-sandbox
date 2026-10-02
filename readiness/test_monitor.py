from oracle_bridge import require_guard
require_guard()
import unittest
from monitor import observe_slot, observe_metrics
DUE = '2026-10-02T12:00:00Z'
LATE = '2026-10-02T12:00:01Z'


class MonitorTests(unittest.TestCase):
    def test_before_deadline_pending(self):
        self.assertEqual(observe_slot({},DUE,'2026-10-02T11:59:59Z')['state'],'pending')

    def test_at_deadline_pending(self):
        self.assertEqual(observe_slot({},DUE,DUE)['state'],'pending')

    def test_deadline_exceeded_not_missed(self):
        result = observe_slot({},DUE,LATE)
        self.assertEqual(result['state'],'deadline_exceeded')
        self.assertFalse(result['auto_resend'])

    def test_missed_requires_explicit_evidence(self):
        self.assertEqual(observe_slot({'status':'missed','evidence_id':'metric-fixture'},DUE,LATE)['state'],'missed')
        with self.assertRaises(ValueError): observe_slot({'status':'missed'},DUE,LATE)

    def test_unknown_retained_after_deadline(self):
        result = observe_slot({'status':'unknown'},DUE,LATE)
        self.assertEqual(result['state'],'unknown')
        self.assertEqual(result['action'],'manual_reconciliation')
        self.assertFalse(result['auto_resend'])

    def test_collected_after_deadline_stays_collected(self):
        result = observe_slot({'status':'collected','evidence_id':'metric-fixture'},DUE,LATE)
        self.assertEqual(result['state'],'collected')
        self.assertTrue(result['deadline_exceeded'])
        self.assertEqual(result['action'],'no_op')

    def test_collected_without_evidence_rejected(self):
        with self.assertRaises(ValueError): observe_slot({'status':'collected'},DUE,LATE)

    def test_timezone_equivalence(self):
        self.assertEqual(observe_slot({},DUE,'2026-10-02T21:00:00+09:00')['state'],'pending')

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError): observe_slot({},'2026-10-02T12:00:00',LATE)

    def test_invalid_time_rejected(self):
        with self.assertRaises(ValueError): observe_slot({},'invalid',LATE)

    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError): observe_slot({'status':'failed'},DUE,LATE)

    def test_raw_response_not_accepted(self):
        with self.assertRaises(ValueError): observe_slot({'status':'unknown','raw_response':{}},DUE,LATE)

    def test_independent_1h_24h_without_invented_zero(self):
        results = observe_metrics({'1h':{'observation':{'status':'collected','evidence_id':'metric-1h'},'deadline':DUE},
                                   '24h':{'observation':{'status':'unknown'},'deadline':DUE}},LATE)
        self.assertEqual(results['1h']['state'],'collected')
        self.assertEqual(results['24h']['state'],'unknown')
        self.assertNotIn('views',str(results))
        self.assertTrue(all(not r['auto_resend'] and not r['posting_permitted'] for r in results.values()))

    def test_both_slots_required(self):
        with self.assertRaises(ValueError): observe_metrics({},LATE)

    def test_path_traversal_evidence_rejected(self):
        with self.assertRaises(ValueError): observe_slot({'status':'collected','evidence_id':'../job'},DUE,LATE)
