from oracle_bridge import require_guard
require_guard()
import copy
import json
from pathlib import Path
import unittest
from typing import Any
from oracle_bridge import oracle
from parity import (CATEGORIES, validate_improvement, improvement_guidance, normalize_script,
                    render_payload, pipeline_inputs, validate_pipeline_inputs, offline_e2e)
from offline_readiness import FLAGS

HERE = Path(__file__).parent
SOURCE = json.loads((HERE / 'parity_sources.json').read_text())
FIXTURE = json.loads((HERE / 'fixture.json').read_text())
GOLDEN = json.loads((HERE / 'parity_fixture.json').read_text())


def script():
    return copy.deepcopy({k:v for k,v in FIXTURE.items() if k != 'theme'})


def feedback(value='改善案'):
    return {'analysis': '固定fixture', 'improvement_actions': {key: value for key in CATEGORIES}}


def response(value='改善案'):
    return {'statusCode': 200, 'body': {'status': 'ready', **feedback(value)}}



class ImprovementTests(unittest.TestCase):
    def test_producer_independent_source_oracle_boundaries(self):
        namespace = {'Any': Any, 'CATEGORIES': tuple(SOURCE['categories'])}
        exec(SOURCE['producer_validator'], namespace)
        cases = [feedback(), feedback('x'*180), feedback('x'*181), feedback('😀'*180),
                 feedback(''), feedback(' '), feedback('line\nbreak'), None, [], {}]
        extra = feedback(); extra['improvement_actions']['extra'] = 'x'; cases.append(extra)
        missing = feedback(); del missing['improvement_actions']['hook']; cases.append(missing)
        typed = feedback(); typed['improvement_actions']['cta'] = 3; cases.append(typed)
        for analysis in ('', 'x'*250, 'x'*251, 9):
            case = feedback(); case['analysis'] = analysis; cases.append(case)
        for case in cases:
            with self.subTest(case_type=type(case).__name__):
                self.assertEqual(validate_improvement(case), namespace['validate_ai'](case))

    def test_producer_does_not_mutate_input(self):
        f = feedback(); result = validate_improvement(f)
        result['improvement_actions']['hook'] = 'changed'
        self.assertEqual(f['improvement_actions']['hook'], '改善案')

    def test_consumer_source_oracle_edge_cases(self):
        cases = [response(), response('x'*240), response('x'*241), response('😀'*120),
                 response('😀'*121), response(' '), response('line\nbreak'), response('x\x00'),
                 response('\ufefftrim\ufeff'), response('\x85'), response('\u2028trim\u2029'),
                 {}, {'statusCode': '200', 'body': response()['body']},
                 {'statusCode': 500, 'body': response()['body']},
                 {'body': json.dumps(response()['body'])},
                 {'body': {'data': response()['body']}}, {'data': response()['body']},
                 {'body': 'invalid json'}, {'body': []}]
        extra = response(); extra['body']['improvement_actions']['extra'] = 'ok'; cases.append(extra)
        missing = response(); del missing['body']['improvement_actions']['hook']; cases.append(missing)
        unready = response(); unready['body']['status'] = 'pending'; cases.append(unready)
        expected = oracle([{'op': 'guidance', 'input': c} for c in cases])
        for case, value in zip(cases, expected):
            with self.subTest(body_type=type(case.get('body')).__name__):
                self.assertEqual(improvement_guidance(case), value)

    def test_stages_have_distinct_limits(self):
        self.assertIsNone(validate_improvement(feedback('x'*200)))
        self.assertTrue(improvement_guidance(response('x'*200)))

    def test_missing_feedback_does_not_block_e2e(self):
        result = offline_e2e(FIXTURE['theme'], {'output': script()}, 'yt-900001-1790942400000', dict.fromkeys(FLAGS, True))
        self.assertEqual(result['improvement_guidance'], '')
        self.assertFalse(result['posting_permitted'])


class TransformationTests(unittest.TestCase):
    def setUp(self):
        self.wrapped = {'output': script(), 'discarded': 'not carried'}

    def test_normalization_exact_node_oracle(self):
        expected = oracle([{'op': 'normalize', 'input': self.wrapped}])[0]
        self.assertEqual(normalize_script(self.wrapped), expected)
        self.assertEqual(expected, GOLDEN['normalized_expected'])
        self.assertEqual(set(expected), {'title','hook','narration','scenes','captions','bgm'})

    def test_multiple_captions_indices_and_timing(self):
        self.wrapped['output']['scenes'].append({**script()['scenes'][0], 'start':5, 'end':10, 'caption':'二つ目'})
        actual = normalize_script(self.wrapped)
        self.assertEqual(actual, oracle([{'op':'normalize', 'input':self.wrapped}])[0])
        self.assertEqual(actual['captions'][1], {'index':2,'start_seconds':5,'end_seconds':10,'text':'二つ目'})

    def test_normalization_immutable(self):
        before = copy.deepcopy(self.wrapped)
        normalized = normalize_script(self.wrapped)
        normalized['scenes'][0]['caption'] = 'changed'
        self.assertEqual(self.wrapped, before)

    def test_renderer_payload_exact_node_oracle(self):
        normalized = normalize_script(self.wrapped)
        expected = oracle([{'op':'render', 'input':normalized}])[0]
        self.assertEqual(render_payload(normalized), expected)
        self.assertEqual(expected, GOLDEN['render_expected'])

    def test_pipeline_dispatch_exact_expression_oracle(self):
        payload = render_payload(normalize_script(self.wrapped))
        actual = pipeline_inputs(payload, 'yt-900001-1790942400000')
        expected = oracle([{'op':'dispatch','input':{**payload,'job_id':'yt-900001-1790942400000'}}])[0]
        self.assertEqual({'ref':'main','inputs':actual}, expected)
        self.assertEqual(actual, GOLDEN['pipeline_inputs_expected'])
        self.assertEqual(set(actual), set(SOURCE['pipeline_inputs']))
        self.assertEqual(len(actual), 18)

    def test_boolean_inputs_are_boolean(self):
        inputs = pipeline_inputs(render_payload(normalize_script(self.wrapped)), 'yt-900001-1790942400000')
        for key in ('made_for_kids','contains_synthetic_media','notify_subscribers'):
            self.assertIs(inputs[key], False)

    def test_pipeline_unknown_field_rejected(self):
        inputs = pipeline_inputs(render_payload(normalize_script(self.wrapped)), 'yt-900001-1790942400000')
        inputs['TEST_ONLY'] = True
        with self.assertRaisesRegex(ValueError,'pipeline_fields'): validate_pipeline_inputs(inputs)

    def test_pipeline_missing_field_rejected(self):
        inputs = pipeline_inputs(render_payload(normalize_script(self.wrapped)), 'yt-900001-1790942400000')
        del inputs['job_id']
        with self.assertRaisesRegex(ValueError,'pipeline_fields'): validate_pipeline_inputs(inputs)

    def test_pipeline_string_boolean_rejected(self):
        inputs = pipeline_inputs(render_payload(normalize_script(self.wrapped)), 'yt-900001-1790942400000')
        inputs['made_for_kids'] = 'false'
        with self.assertRaisesRegex(ValueError,'pipeline_boolean'): validate_pipeline_inputs(inputs)

    def test_pipeline_unknown_privacy_rejected(self):
        inputs = pipeline_inputs(render_payload(normalize_script(self.wrapped)), 'yt-900001-1790942400000')
        inputs['privacy_status'] = 'unknown'
        with self.assertRaisesRegex(ValueError,'pipeline_choice'): validate_pipeline_inputs(inputs)

    def test_pipeline_payload_bound(self):
        inputs = pipeline_inputs(render_payload(normalize_script(self.wrapped)), 'yt-900001-1790942400000')
        inputs['description'] = '😀'*40000
        with self.assertRaisesRegex(ValueError,'pipeline_payload_size'): validate_pipeline_inputs(inputs)

    def test_invalid_identifier_rejected(self):
        with self.assertRaises(ValueError): pipeline_inputs({}, '../job')

    def test_e2e_same_identity_for_manual_and_schedule(self):
        args = (FIXTURE['theme'], self.wrapped, 'yt-900001-1790942400000', dict.fromkeys(FLAGS,True))
        manual = offline_e2e(*args, entry_kind='manual', feedback=response())
        scheduled = offline_e2e(*args, entry_kind='schedule', feedback=response())
        self.assertEqual(manual['content_fingerprint'], scheduled['content_fingerprint'])
        self.assertEqual(manual['pipeline_inputs'], scheduled['pipeline_inputs'])
        self.assertEqual(manual['job_id'], scheduled['job_id'])
        self.assertFalse(manual['posting_permitted'])
        self.assertTrue(all(manual['safety'].values()))

    def test_e2e_different_content_changes_fingerprint(self):
        args = (FIXTURE['theme'], self.wrapped, 'yt-900001-1790942400000', dict.fromkeys(FLAGS,True))
        original = offline_e2e(*args)
        self.wrapped['output']['narration'] += '変更。'
        self.assertNotEqual(original['content_fingerprint'], offline_e2e(*args)['content_fingerprint'])

    def test_e2e_unsafe_flag_rejected(self):
        for key in FLAGS:
            flags = dict.fromkeys(FLAGS,True); flags[key] = False
            with self.assertRaises(ValueError): offline_e2e(FIXTURE['theme'],self.wrapped,'yt-900001-1790942400000',flags)

    def test_e2e_invalid_entry_rejected(self):
        with self.assertRaises(ValueError): offline_e2e(FIXTURE['theme'],self.wrapped,'yt-900001-1790942400000',dict.fromkeys(FLAGS,True),'auto_retry')
