import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const root=new URL('../',import.meta.url);
const read=p=>readFileSync(new URL(p,root));
const json=p=>JSON.parse(read(p));
const h=value=>createHash('sha256').update(value).digest('hex');
const folder='readiness/manual_fixture/';
const fixed=json(folder+'fixed-sha256.json');
function sorted(v){if(Array.isArray(v))return v.map(sorted);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,sorted(v[k])]));return v;}
test('manual fixture raw hash and semantic script hash remain distinct and pinned',()=>{
 const raw=read(folder+'manual-japanese-script-fixture-v1.json');assert.equal(h(raw),fixed.raw_fixture_sha256);
 assert.equal(h(JSON.stringify(sorted(JSON.parse(raw).output))),fixed.script_sha256);
 assert.equal(fixed.script_sha256,'9077ccd4b61ff3bcdadcccaaea90219377acfd4abf19ebd414af36f7eb7c0b8b');
});
test('cross-language normalized contract and render canonical byte hashes match',()=>{
 for(const [file,key]of [['script.canonical.json','script_sha256'],['normalized-result.canonical.json','normalized_contract_sha256'],['render-payload.canonical.json','render_payload_sha256'],['manual-request.canonical.json','manual_request_sha256'],['generation-output.canonical.json','normalized_output_sha256'],['input-contract.canonical.json','input_request_contract_sha256'],['checkpoint.canonical.json','checkpoint_sha256']]){
  const raw=read(folder+file);assert.equal(h(raw),fixed[key]);assert.equal(raw.toString(),JSON.stringify(sorted(JSON.parse(raw))));
 }
});
test('manual provenance and provider identity are separate and never reach renderer',()=>{
 const result=json(folder+'normalized-result.canonical.json');assert.equal(result.source,'manual_fixture');assert.equal(result.provider_identity,null);assert.equal(result.model_identity,null);
 const p=json(folder+'render-payload.canonical.json');assert.equal(p.captions.length,3);assert.deepEqual(p.output,{format:'mp4',width:1080,height:1920,fps:30});
 for(const key of ['source','provider_identity','model_identity','request_sha256','oauth_secret_name'])assert(!Object.hasOwn(p,key));
});
test('production source snapshot is immutable, code-pinned and read only',()=>{
 const source=json('readiness/manual-fixture-production-sources.json');const pins=json('readiness/manual-fixture-source-pins.json');assert.equal(source.production_sha,pins.production_sha);
 for(const [path,sha] of Object.entries(pins.paths))assert.equal(h(source.sources[path]),sha);
 for(const value of [pins.generation_source,pins.parity_source])assert.equal(h(read(value.path)),value.raw_sha256);
 assert.equal(source.read_only,true);
});
test('manual render and migration workflows remain hard disabled without credential paths',()=>{
 for(const path of ['.github/workflows/plm-manual-fixture-render-once.yml','.github/workflows/plm-provider-neutral-backend-migration-once.yml']){
  const text=read(path).toString();assert.match(text,/if: false/);assert.match(text,/allow: 'false'/);assert.match(text,/execution_approved: 'false'/);
  for(const flag of ['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'])assert(text.includes(`${flag}: 'true'`));
  assert(!/secrets\.|curl|wrangler|render\.py|workflow_dispatches/.test(text));
 }
});
