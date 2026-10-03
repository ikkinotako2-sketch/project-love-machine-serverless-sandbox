"""Execute frozen JSON SQL against SQLite only; never remote D1 evidence."""
import json, sqlite3, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PLAN=json.loads((ROOT/'serverless/atomicity-test-plan.json').read_text())
class FixedAtomicityPlan(unittest.TestCase):
 def execute(self,winner):
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
  db.executescript((ROOT/'serverless/migrations/0002_backend_probe_v1.sql').read_text())
  vals={'T0':100,'T1':101,'T2':102,'WINNER':winner,'LOSER':'contender_b' if winner=='contender_a' else 'contender_a'}
  steps=PLAN['steps'].copy()
  if winner=='contender_b':steps[2:4]=[steps[3],steps[2]]
  counts=[]
  for step in steps:
   before=db.total_changes
   db.execute(step['sql'],[vals.get(x,x) for x in step['params']]);counts.append(db.total_changes-before)
   if step['expected_changes'] is not None:self.assertEqual(counts[-1],step['expected_changes'])
  self.assertEqual(sum(counts),3);self.assertEqual(len(counts),9)
  row=dict(db.execute('SELECT * FROM backend_probe_v1').fetchone())
  self.assertEqual(row,{k:vals.get(v,v) for k,v in PLAN['expected_final_row'].items()})
  return db
 def test_a_wins_exact_json_sql(self):self.execute('contender_a').close()
 def test_b_wins_exact_json_sql(self):self.execute('contender_b').close()
 def test_fingerprint_mutation_trigger_rejects_locally(self):
  db=self.execute('contender_a')
  with self.assertRaises(sqlite3.IntegrityError):db.execute("UPDATE backend_probe_v1 SET content_fingerprint=?,version=4",['0'*64])
  db.close()
 def test_delete_not_in_fixed_templates(self):
  self.assertTrue(all('DELETE' not in x['sql'].upper() for x in PLAN['steps']))
