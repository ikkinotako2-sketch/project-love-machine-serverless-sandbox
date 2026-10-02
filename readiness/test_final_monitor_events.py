"""Observation-driven monitor regression cases; mandatory offline guard."""
from oracle_bridge import require_guard
require_guard()
from test_final_boundaries import Setup, T, METRICS
from final_readiness import command_view


class MonitorEventTests(Setup):
    def view(self, now):
        row=self.row()['record']
        loop=self.hub.loop.tick((row.intent.platform,row.intent.account_id,row.job_id),now)
        return command_view(self.row(),now,loop=loop,workflow_conclusion='success')

    def test_pending_hour_has_expected_time_and_deadline(self):
        self.succeeded();v=self.view(T)
        self.assertEqual(v['next_expected_event'],'metrics_1h_evidence')
        self.assertEqual((v['expected_time'],v['deadline']),(T+3600,T+10800))
        self.assertEqual(v['health'],'incomplete')

    def test_collected_hour_advances_to_day(self):
        self.succeeded();self.call('metrics',self.metric('1h'),T+3600)
        v=self.view(T+3600)
        self.assertEqual(v['next_expected_event'],'metrics_24h_evidence')
        self.assertEqual(v['expected_time'],T+86400)
        self.assertEqual(v['last_durable_checkpoint'],'metrics_checkpoint')

    def test_pending_overdue_is_not_fabricated_missed(self):
        self.succeeded();v=self.view(T+10801)
        self.assertTrue(v['deadline_exceeded'])
        self.assertEqual(v['metrics']['1h']['observation_status'],'pending')
        self.assertEqual(v['next_safe_action'],'inspect_only')

    def test_explicit_missed_is_not_healthy_workflow_success(self):
        self.succeeded()
        self.call('metrics',self.metric('1h',status='missed',metrics=None,observed_at=T+10801),T+10801)
        self.call('metrics',self.metric(),T+86400)
        v=self.view(T+86400)
        self.assertEqual(v['health'],'missed')
        self.assertEqual(v['next_safe_action'],'inspect_only')
        self.assertEqual(v['next_expected_event'],'improvement_fixture')

    def test_unknown_reconciliation_has_priority_over_pending_day(self):
        self.succeeded()
        self.call('metrics',self.metric('1h',status='unknown',metrics=None),T+3600)
        v=self.view(T+3600)
        self.assertEqual(v['next_expected_event'],'manual_reconciliation')
        self.assertIsNone(v['expected_time'])
        self.assertTrue(v['manual_reconciliation_required'])

    def collect(self):
        self.succeeded();self.call('metrics',self.metric('1h'),T+3600)
        self.call('metrics',self.metric(),T+86400)

    def test_both_collected_expect_improvement(self):
        self.collect();v=self.view(T+86400)
        self.assertEqual(v['next_expected_event'],'improvement_fixture')
        self.assertIsNone(v['deadline'])
        self.assertFalse(v['live_permitted'])

    def test_improvement_checkpoint_precedes_terminal(self):
        self.collect();self.improve();v=self.view(T+86400)
        self.assertEqual(v['last_durable_checkpoint'],'improvement_checkpoint')
        self.assertEqual(v['next_expected_event'],'next_intent_fixture')

    def test_planned_next_requires_review_never_claim(self):
        self.collect();self.improve();self.plan();v=self.view(T+86400)
        self.assertEqual(v['last_durable_checkpoint'],'next_intent_checkpoint')
        self.assertEqual(v['next_expected_event'],'next_intent_review')
        self.assertIn('claim_next_intent',v['unsafe_automatic_action'])
