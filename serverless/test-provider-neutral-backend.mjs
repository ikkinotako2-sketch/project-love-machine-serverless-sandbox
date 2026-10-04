import test from 'node:test';
import assert from 'node:assert/strict';
import {validate,PINS} from './provider-neutral-backend-contract.mjs';
import {readFileSync} from 'node:fs';
test('provider-neutral fixed files and STOP budgets are pinned',()=>assert.equal(validate().remote_applications,0));
test('candidate contains only new namespace CREATE graph',()=>{
 const sql=readFileSync(new URL('./migrations/0008_provider_neutral_roundtrip_backend.sql',import.meta.url),'utf8');
 assert.equal((sql.match(/CREATE TABLE /g)||[]).length,5);
 assert.equal((sql.match(/CREATE TRIGGER /g)||[]).length,11);
 assert(!/\b(DROP|DELETE|ALTER|RENAME)\b/i.test(sql));
 assert(!sql.includes('plm_rt_v1_'));
 assert.equal(Object.keys(PINS).length,4);
});
test('migration placeholder is hard disabled with no credential transport',()=>{
 const text=readFileSync(new URL('../.github/workflows/plm-provider-neutral-backend-migration-once.yml',import.meta.url),'utf8');
 assert.match(text,/if: false/);assert.match(text,/allow: 'false'/);assert.match(text,/execution_approved: 'false'/);
 assert(!/secrets\.|curl|fetch\(|wrangler/.test(text));
});
