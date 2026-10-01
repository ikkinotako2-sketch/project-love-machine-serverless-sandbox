import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import {bindingConfig, validateInspection} from './d1-setup.mjs';
const read = p => readFileSync(new URL(p, import.meta.url),'utf8');
const migration = read('./migrations/0001_test_jobs.sql');
const inspectSQL = read('./verify-d1.sql');
function snapshot(db) {
 return {tableSql:db.prepare("SELECT sql FROM sqlite_master WHERE name='test_jobs'").get()?.sql,
  columns:db.prepare('PRAGMA table_info(test_jobs)').all(),
  jobCount:db.prepare('SELECT COUNT(*) AS count FROM test_jobs').get().count};
}
function record(db,state='unknown') {
 db.prepare('INSERT INTO test_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)').run(
  'test','test_reference_001','test-preserved','a'.repeat(64),'mock-owner',state,3,'ambiguous_dispatch',null,1,2);
}
test('migration exactly matches canonical schema and creates empty ready schema',()=>{
 assert.equal(migration,read('./schema.sql'));
 const db=new DatabaseSync(':memory:');try {
  db.exec(migration);assert.deepEqual(validateInspection(snapshot(db)),{schema:'pass',empty:'pass',posting_permission:false});
 }finally{db.close();}
});
test('initialization can repeat without deleting or resetting existing unknown job',()=>{
 const db=new DatabaseSync(':memory:');try {
  db.exec(migration);record(db);const before=db.prepare('SELECT * FROM test_jobs').all();
  db.exec(migration);assert.deepEqual(db.prepare('SELECT * FROM test_jobs').all(),before);
  assert.throws(()=>validateInspection(snapshot(db)),/existing_job/);
 }finally{db.close();}
});
test('DB constraints reject duplicate identity, non-test platform, invalid state and version',()=>{
 const db=new DatabaseSync(':memory:');try {
  db.exec(migration);record(db);assert.throws(()=>record(db));
  assert.throws(()=>db.exec("UPDATE test_jobs SET platform='youtube'"));
  assert.throws(()=>db.exec("UPDATE test_jobs SET account_id='other'"));
  assert.throws(()=>db.exec("UPDATE test_jobs SET state='initialized'"));
  assert.throws(()=>db.exec('UPDATE test_jobs SET version=0'));
 }finally{db.close();}
});
test('read-only verification statements cannot consume the one-job slot',()=>{
 const statements=inspectSQL.replace(/--[^\n]*/g,'').split(';').map(s=>s.trim()).filter(Boolean);
 assert.equal(statements.length,4);
 assert.ok(statements.every(s=>/^(SELECT\b|PRAGMA table_info\(test_jobs\)$)/i.test(s)));
 const db=new DatabaseSync(':memory:');try {
  db.exec(migration);db.exec('PRAGMA query_only=ON');
  for(const s of statements) db.prepare(s).all();
  assert.equal(snapshot(db).jobCount,0);
 }finally{db.close();}
});
test('inspection rejects missing schema, wrong constraints, extra secret column, invalid counts',()=>{
 const db=new DatabaseSync(':memory:');try {
  db.exec(migration);const s=snapshot(db);
  assert.throws(()=>validateInspection({...s,tableSql:undefined}));
  assert.throws(()=>validateInspection({...s,tableSql:s.tableSql.replace("CHECK(platform='test')",'')}));
  assert.throws(()=>validateInspection({...s,columns:[...s.columns,{name:'access_token',type:'TEXT',notnull:0,pk:0}]}));
  for(const jobCount of [1,-1,null,'0',NaN]) assert.throws(()=>validateInspection({...s,jobCount}));
  db.exec('ALTER TABLE test_jobs ADD COLUMN access_token TEXT');assert.throws(()=>validateInspection(snapshot(db)));
 }finally{db.close();}
});
test('binding config is isolated, stopped, credential-free and migration-enabled',()=>{
 const config=bindingConfig('11111111-1111-4111-8111-111111111111');
 assert.equal(config.name,'plm-serverless-sandbox-control');assert.equal(config.main,'worker.mjs');
 assert.deepEqual(config.vars,{TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'true'});
 assert.equal(config.d1_databases.length,1);assert.deepEqual(config.d1_databases[0],{
  binding:'DB',database_name:'plm-serverless-sandbox-state',database_id:'11111111-1111-4111-8111-111111111111',migrations_dir:'migrations'});
 assert.ok(!/token|secret|authorization|password|cron|queues/i.test(JSON.stringify(config)));
 config.vars.EMERGENCY_STOP='false';assert.equal(bindingConfig('11111111-1111-4111-8111-111111111111').vars.EMERGENCY_STOP,'true');
});
test('binding config refuses placeholders, traversal, URLs and secret-shaped identifiers',()=>{
 for(const id of [null,undefined,'../db','https://mock.invalid','Bearer mock','ghp_mock','REPLACE_ONLY_AFTER_DATABASE_EXISTENCE_VERIFICATION',''])
  assert.throws(()=>bindingConfig(id),/invalid_database_id/);
});
