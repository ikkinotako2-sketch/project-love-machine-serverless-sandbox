"""Offline Actions condition oracle; never dispatches a workflow.

Status semantics: https://docs.github.com/en/actions/reference/workflows-and-actions/expressions
Reachable legacy graph: initialize -> render -> youtube. Render success implies
initialize success. Legacy has no checkpoint dependency; revised checkpoint is
skipped when context is empty. This is a documented-semantics model, not a claim
of running GitHub's private scheduler or a live cancellation test.
"""
from oracle_bridge import require_guard
require_guard()
import hashlib
import itertools
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent / 'production-candidate'
OLD = "always() && needs.render.result == 'success' && (inputs.serverless_context == '' || needs.checkpoint_render.result == 'success')"
NEW = "!cancelled() && needs.render.result == 'success' && (inputs.serverless_context == '' || needs.checkpoint_render.result == 'success')"
STATES = ('success', 'failure', 'cancelled', 'skipped')

def expression():
    source = (ROOT/'revised-source/.github/workflows/youtube-pipeline.yml').read_text()
    return re.search(r'^  youtube:\n    if: \$\{\{ (.*?) \}\}', source, re.M).group(1)

def interpret(expr, values):
    """Small independent parser of the actual expression bytes, with no eval/IO."""
    tokens = re.findall(r"&&|\|\||==|!|\(|\)|'[^']*'|[A-Za-z_][A-Za-z0-9_.]*", expr)
    if ''.join(tokens) != re.sub(r'\s+', '', expr):
        raise ValueError('unsupported expression')
    pos = 0
    def atom():
        nonlocal pos
        token = tokens[pos]; pos += 1
        if token == '!': return not atom()
        if token == '(':
            value = disjunction()
            assert tokens[pos] == ')'; pos += 1
            return value
        if token in ('always', 'cancelled'):
            assert tokens[pos:pos+2] == ['(', ')']; pos += 2
            return True if token == 'always' else values['cancelled']
        if token.startswith("'"): return token[1:-1]
        return values[token]
    def equality():
        nonlocal pos
        value = atom()
        if pos < len(tokens) and tokens[pos] == '==':
            pos += 1; value = value == atom()
        return value
    def conjunction():
        nonlocal pos
        value = equality()
        while pos < len(tokens) and tokens[pos] == '&&':
            pos += 1; right = equality(); value = bool(value and right)
        return value
    def disjunction():
        nonlocal pos
        value = conjunction()
        while pos < len(tokens) and tokens[pos] == '||':
            pos += 1; right = conjunction(); value = bool(value or right)
        return value
    result = disjunction()
    assert pos == len(tokens)
    return bool(result)

def actual(context, render, checkpoint, cancelled):
    return interpret(expression(), {'inputs.serverless_context': context,
        'needs.render.result': render, 'needs.checkpoint_render.result': checkpoint,
        'cancelled': cancelled})

def legacy_oracle(render, cancelled):
    # Default success(): dependency succeeds and workflow is not cancelled.
    return render == 'success' and not cancelled

class RevisedSchedulingTests(unittest.TestCase):
    def check(self, context, render, checkpoint, cancelled, expected):
        self.assertEqual(actual(context, render, checkpoint, cancelled), expected)
        if context == '':
            self.assertEqual(actual(context, render, checkpoint, cancelled), legacy_oracle(render, cancelled))
    def test_01_legacy_normal_success(self): self.check('', 'success', 'skipped', False, True)
    def test_02_legacy_render_failure(self): self.check('', 'failure', 'skipped', False, False)
    def test_03_legacy_render_cancelled(self): self.check('', 'cancelled', 'skipped', False, False)
    def test_04_workflow_cancellation(self): self.check('', 'success', 'skipped', True, False)
    def test_05_legacy_upstream_skipped(self): self.check('', 'skipped', 'skipped', False, False)
    def test_06_serverless_success(self): self.check('BOUND', 'success', 'success', False, True)
    def test_07_checkpoint_failure(self): self.check('BOUND', 'success', 'failure', False, False)
    def test_08_checkpoint_cancelled(self): self.check('BOUND', 'success', 'cancelled', False, False)
    def test_09_checkpoint_unexpected_skip(self): self.check('BOUND', 'success', 'skipped', False, False)
    def test_10_cancellation_after_render_no_new_start(self):
        for context, cp in (('', 'skipped'), ('BOUND', 'success')):
            self.assertTrue(actual(context, 'success', cp, False))
            self.assertFalse(actual(context, 'success', cp, True))
    def test_exhaustive_64_status_combinations(self):
        for context, render, cp, cancelled in itertools.product(('', 'BOUND'), STATES, STATES, (False, True)):
            with self.subTest(context=context, render=render, checkpoint=cp, cancelled=cancelled):
                expected = not cancelled and render == 'success' and (context == '' or cp == 'success')
                self.check(context, render, cp, cancelled, expected)
    def test_old_patch_regression_detected(self):
        self.assertTrue(interpret(OLD, {'inputs.serverless_context':'', 'needs.render.result':'success', 'needs.checkpoint_render.result':'skipped', 'cancelled':True}))
        self.assertFalse(legacy_oracle('success', True))
    def test_exact_expression_no_cancellation_bypass(self):
        self.assertEqual(expression(), NEW)
        self.assertNotIn('always', expression())
    def test_old_patch_preserved_and_new_scope(self):
        old = (ROOT/'production.patch').read_bytes()
        new = (ROOT/'production-revised.patch').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(), '841bb6315b8b2a36e3a14e127bc082f8483f11461493b8f7092c44b83f40e0f4')
        self.assertEqual(new, old.replace(OLD.encode(), NEW.encode()))
        self.assertEqual(re.findall(r'^\+\+\+ b/(.+)$', new.decode(), re.M), [
            '.github/workflows/youtube-adapter.yml', '.github/workflows/youtube-pipeline.yml', 'plm/entrypoints/yt_serverless_candidate.py'])
    def test_candidate_only_changes_one_condition(self):
        old = (ROOT/'source/.github/workflows/youtube-pipeline.yml').read_text()
        new = (ROOT/'revised-source/.github/workflows/youtube-pipeline.yml').read_text()
        self.assertEqual(new, old.replace(OLD, NEW))
        base = (ROOT/'base/.github/workflows/youtube-pipeline.yml').read_text()
        self.assertRegex(base, r'  youtube:\n    needs: render\n    uses:')
        # Exact base snapshots and render graph remain unchanged.
        self.assertEqual(hashlib.sha256(base.encode()).hexdigest(), '5f3550854efc85ec46c6e4bbb5061c009530f6760f3ac1ebc5c64f63aa2b4928')
        self.assertIn('  render:\n    needs: initialize\n', new)
        self.assertIn('  checkpoint_render:\n    if: inputs.serverless_context != \'\'\n    needs: render\n', new)

if __name__ == '__main__': unittest.main()
