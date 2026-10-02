import copy
import json
import pathlib
import unittest
from offline_readiness import FLAGS, script_to_render, storage_envelope, recovery_hint


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.script = json.loads(pathlib.Path(__file__).with_name('fixture.json').read_text())
        self.theme = self.script.pop('theme')
        self.flags = dict.fromkeys(FLAGS, True)

    def render(self, **kw):
        return script_to_render(kw.get('theme', self.theme), kw.get('script', self.script),
                                kw.get('account', 'youtube-test-001'), kw.get('job', 'offline-001'),
                                kw.get('flags', self.flags))

    def test_fixture_maps_render_contract_without_posting(self):
        r = self.render()
        self.assertFalse(r['posting_permitted'])
        self.assertEqual(r['render_payload']['output']['width'], 1080)
        self.assertEqual(r['render_payload']['captions'][0]['text'], '固定fixture')

    def test_fingerprint_stable_across_job_retry(self):
        self.assertEqual(self.render()['content_fingerprint'], self.render(job='offline-002')['content_fingerprint'])

    def test_fingerprint_changes_with_account_or_content(self):
        old = self.render()['content_fingerprint']
        self.assertNotEqual(old, self.render(account='youtube-test-002')['content_fingerprint'])
        self.assertNotEqual(old, self.render(theme='別の固定テーマ')['content_fingerprint'])

    def test_defensive_copy(self):
        result = self.render()
        self.script['scenes'][0]['caption'] = '変更'
        self.assertEqual(result['render_payload']['scenes'][0]['caption'], '固定fixture')

    def test_each_safety_flag_required(self):
        for key in FLAGS:
            flags = self.flags.copy(); flags[key] = False
            with self.assertRaises(ValueError): self.render(flags=flags)

    def test_string_true_not_accepted(self):
        with self.assertRaises(ValueError): self.render(flags=dict.fromkeys(FLAGS, 'true'))

    def test_unknown_field_rejected(self):
        self.script['access_token'] = 'dummy'
        with self.assertRaises(ValueError): self.render()

    def test_secret_shaped_text_rejected_without_echo(self):
        self.script['narration'] = 'Bearer dummy-offline'
        with self.assertRaisesRegex(ValueError, '^unsafe_text$'): self.render()

    def test_traversal_rejected(self):
        with self.assertRaises(ValueError): self.render(job='../escape')

    def test_account_platform_mismatch_rejected(self):
        with self.assertRaises(ValueError): self.render(account='tiktok-test-001')

    def test_missing_narration_rejected(self):
        self.script['narration'] = ''
        with self.assertRaises(ValueError): self.render()

    def test_overlap_rejected(self):
        self.script['scenes'].append(copy.deepcopy(self.script['scenes'][0]))
        with self.assertRaises(ValueError): self.render()

    def test_nonfinite_and_bool_duration_rejected(self):
        for invalid in (float('nan'), float('inf'), True):
            self.script['scenes'][0]['end'] = invalid
            with self.assertRaises(ValueError): self.render()

    def test_unverified_storage_never_passes(self):
        self.assertEqual(storage_envelope(100, 1, 50_000_000, 1)['status'], 'UNVERIFIED')

    def test_hundred_account_storage_exceeds_conservative_allowance(self):
        r = storage_envelope(100, 1, 50_000_000, 1, verified_allowance_bytes=500*1024**2)
        self.assertEqual(r['required_bytes'], 5_000_000_000)
        self.assertEqual(r['status'], 'BLOCKED')

    def test_existing_storage_and_retention_counted(self):
        r = storage_envelope(1, 1, 20, 2, 60, 100)
        self.assertEqual(r['required_bytes'], 100)
        self.assertEqual(r['status'], 'WITHIN_ASSUMPTIONS')
        self.assertFalse(r['posting_permitted'])

    def test_negative_and_bool_budget_rejected(self):
        for invalid in (-1, True, 0):
            with self.assertRaises(ValueError): storage_envelope(invalid, 1, 1, 1)

    def test_ambiguous_states_never_initialize_even_without_publish_id(self):
        for state in ('initializing', 'unknown', 'reconciliation_required'):
            r = recovery_hint(state, False, True)
            self.assertEqual(r['action'], 'manual_reconciliation')
            self.assertFalse(r['initialize_permitted'])

    def test_stale_owner_never_takes_over(self):
        self.assertEqual(recovery_hint('claimed', False, False)['action'], 'blocked_owner')
        self.assertFalse(recovery_hint('processing', True, False)['takeover_permitted'])

    def test_saved_publish_id_is_status_only(self):
        for state in ('initialized', 'transferring', 'processing'):
            self.assertEqual(recovery_hint(state, True, True)['action'], 'status_reconciliation_only')

    def test_terminal_is_noop(self):
        for state in ('succeeded', 'failed'):
            self.assertEqual(recovery_hint(state, True, True)['action'], 'terminal_noop')

    def test_invalid_state_rejected(self):
        with self.assertRaises(ValueError): recovery_hint('retry_initialize', False, True)


if __name__ == '__main__': unittest.main()
