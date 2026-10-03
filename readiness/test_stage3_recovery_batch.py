"""SQLite reference only: these tests do not establish remote D1 acceptance."""
import hashlib,json,re,sqlite3,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/'serverless/migrations/0004_durable_stage2_explicit_batch.sql').read_bytes()
REQUEST=(ROOT/'serverless/stage3-recovery-request.json').read_bytes()
def statements(s):
    out=[];pending=''
    for line in s.splitlines(True):
        pending+=line
        if sqlite3.complete_statement(pending): out.append(pending.strip());pending=''
    if pending.strip(): raise ValueError('incomplete')
    return out
class RecoveryBatchTests(unittest.TestCase):
    def test_fixed_sql_hash(self): self.assertEqual(hashlib.sha256(SQL).hexdigest(),'c2d3c40447490932df83ecf52797d493787cc2a76a4a4efbc1b0a11a633381c4')
    def test_fixed_request_hash(self): self.assertEqual(hashlib.sha256(REQUEST).hexdigest(),'7a22f2ec5eed90e658f934fb6005289752470193a213b084cfb1f21700278d58')
    def test_complete_ddl_count(self): self.assertEqual(len(statements(SQL.decode())),9)
    def test_batch_mapping(self):
        body=json.loads(REQUEST);self.assertEqual(list(body),['batch']);self.assertEqual(len(body['batch']),9)
        for ddl,item in zip(statements(SQL.decode()),body['batch']):
            self.assertEqual(item['params'],[]);self.assertNotIn('\n',item['sql'])
            # Compare token sequences while preserving literal bytes.
            tokens=lambda x:re.findall(r"'(?:''|[^'])*'|\w+|[^\s\w]",x)
            self.assertEqual(tokens(ddl),tokens(item['sql']))
    def test_no_destructive_ddl(self): self.assertIsNone(re.search(r'\b(DROP|DELETE|ALTER|RENAME)\b',SQL.decode(),re.I))
    def test_local_batch_schema_matches_file(self):
        a=sqlite3.connect(':memory:');b=sqlite3.connect(':memory:');a.executescript(SQL.decode())
        for item in json.loads(REQUEST)['batch']: b.execute(item['sql'])
        q="SELECT type,name,tbl_name FROM sqlite_master ORDER BY type,name"
        self.assertEqual(a.execute(q).fetchall(),b.execute(q).fetchall())
        for name,count in [('durable_stage2_job',16),('durable_stage2_checkpoint',11),('durable_stage2_callback',9)]:
            self.assertEqual(a.execute('PRAGMA table_info('+name+')').fetchall(),b.execute('PRAGMA table_info('+name+')').fetchall())
            self.assertEqual(len(a.execute('PRAGMA table_info('+name+')').fetchall()),count)
            self.assertEqual(a.execute('SELECT COUNT(*) FROM '+name).fetchone(),(0,))
    def test_old_sql_preserved(self):
        self.assertEqual(hashlib.sha256((ROOT/'serverless/migrations/0003_durable_stage2_probe.sql').read_bytes()).hexdigest(),'012eae70985512f4672546e8f773ed43392754fc95149192b4b0108daf836686')
    def test_remote_acceptance_unverified(self): self.assertEqual(json.loads((ROOT/'serverless/stage3-recovery-manifest.json').read_text())['remote_support_status'],'UNVERIFIED_UNTIL_SEPARATELY_APPROVED_EXECUTION')
