import {candidate} from './generalized-backend-contract.mjs';
import {ACCOUNT,DB,NAME,CONTRACT,canonical} from './atomicity-schema-audit.mjs';
import {jsonBounded} from './d1-v2-migration.mjs';
const norm=s=>s.map(x=>({...x,sql:x.sql?.trim().replace(/;$/,'')??null})).sort((a,b)=>(a.type+':'+a.name)<(b.type+':'+b.name)?-1:1);
export function classify(schema,details,preserved,c=candidate()){
 if(!preserved)return 'STILL_UNKNOWN';const found=schema.filter(x=>x.name.startsWith(c.plan.namespace)),expected=c.after.new;
 if(found.some(x=>!expected.schema.some(y=>y.name===x.name&&canonical(norm([x]))===canonical(norm([y])))))return 'STILL_UNKNOWN';
 if(!found.length)return 'NOT_APPLIED';
 for(const [t,d] of Object.entries(details))if(canonical(d.columns)!==canonical(expected.columns[t])||canonical(d.indexes)!==canonical(expected.indexes[t])||d.row_count!==0)return 'STILL_UNKNOWN';
 if(found.length!==expected.schema.length)return 'PARTIAL_APPLIED';
 return canonical(norm(schema))===canonical(norm(c.after.schema))&&Object.keys(details).length===5&&Object.values(details).flatMap(d=>d.indexes).length===14?'FULL_APPLIED':'STILL_UNKNOWN';
}
export async function reconcile(e,f=fetch){const c=candidate(),base=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database`,target=base+'/'+DB,out={pass:false,classification:'STILL_UNKNOWN',read_only_calls:0,query_mutations:0,retry:0};
 if(!e.PLM_CF_D1_READ_TOKEN) return out;
 async function api(u,sql){out.read_only_calls++;const r=await f(u,{method:sql?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_READ_TOKEN}`,'Content-Type':'application/json'},...(sql?{body:JSON.stringify({sql,params:[]})}:{})});if(!r.ok)throw Error('GENERALIZED_POST_HTTP_UNKNOWN');const b=await jsonBounded(r,65536);if(b.success!==true)throw Error('GENERALIZED_POST_RESPONSE_UNKNOWN');if(!sql)return b;const q=b.result?.[0];if(b.result?.length!==1||q?.success!==true||!Array.isArray(q.results)||q.results.length>64||q.meta?.served_by_primary!==true||q.meta?.rows_written>0||q.meta?.changed_db===true)throw Error('GENERALIZED_POST_PRIMARY_UNKNOWN');return q.results;}
 try{
 const v=await api('https://api.cloudflare.com/client/v4/user/tokens/verify');if(v.result?.status!=='active')throw Error('GENERALIZED_POST_READ_TOKEN_INACTIVE');
 const inv=[];let total;for(let p=1;p<=100;p++){const b=await api(base+`?page=${p}&per_page=100`),i=b.result_info;if(!Array.isArray(b.result)||i?.page!==p||i.count!==b.result.length||!Number.isSafeInteger(i.total_count))throw Error('GENERALIZED_POST_INVENTORY_UNKNOWN');if(total===undefined)total=i.total_count;if(total!==i.total_count)throw Error('GENERALIZED_POST_INVENTORY_DRIFT');inv.push(...b.result);if(inv.length===total)break;if(!b.result.length||p===100||inv.length>total)throw Error('GENERALIZED_POST_INVENTORY_INCOMPLETE');}
 if(inv.length!==1||inv[0].uuid!==DB||inv[0].name!==NAME)throw Error('GENERALIZED_POST_INVENTORY_NOT_EXACT');out.inventory=c.before.inventory;
 const m=await api(target);if(m.result?.uuid!==DB||m.result?.name!==NAME||!Number.isSafeInteger(m.result.file_size))throw Error('GENERALIZED_POST_SIZE_UNKNOWN');out.database_size_bytes=m.result.file_size;
 const schema=await api(target+'/query',"SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name");out.schema=norm(schema);
 const old=schema.filter(x=>!x.name.startsWith(c.plan.namespace));out.old_schema_unchanged=canonical(norm(old))===canonical(norm(c.before.schema));
 const tc=await api(target+'/query','PRAGMA table_info(test_jobs)'),pc=await api(target+'/query','PRAGMA table_info(backend_probe_v1)'),pi=await api(target+'/query','PRAGMA index_list(backend_probe_v1)');
 out.old_columns_indexes_unchanged=canonical(tc)===canonical(CONTRACT.snapshot.test_jobs_columns)&&canonical(pc)===canonical(CONTRACT.snapshot.probe_columns)&&canonical([...pi].sort((a,b)=>a.name<b.name?-1:1))===canonical(CONTRACT.snapshot.probe_indexes);
 const atomic=await api(target+'/query','SELECT * FROM backend_probe_v1'),jobs=await api(target+'/query','SELECT COUNT(*) AS n FROM test_jobs');out.atomicity_row_unchanged=atomic.length===1&&canonical(atomic[0])===canonical(c.before.atomicity_row);out.atomicity_row=atomic.length===1?atomic[0]:null;out.test_jobs_unchanged=jobs.length===1&&jobs[0].n===0;
 const rows={},details={};for(const t of Object.keys(c.before.stage2_rows)){const cols=await api(target+'/query','PRAGMA table_info('+t+')'),idx=await api(target+'/query','PRAGMA index_list('+t+')');rows[t]=await api(target+'/query','SELECT * FROM '+t);const d=c.before.stage2_details[t];details[t]=canonical(cols)===canonical(d.columns)&&canonical(idx)===canonical(d.indexes);}
 out.stage2_rows=rows;out.stage2_rows_unchanged=canonical(rows)===canonical(c.before.stage2_rows);out.stage2_columns_indexes_unchanged=Object.values(details).every(Boolean);out.kv_schema_unchanged=out.old_schema_unchanged;out.kv_content_status='NOT_APPLICABLE_RESERVED_UNQUERYABLE';
 const n={};for(const t of Object.keys(c.after.new.columns)){if(!schema.some(x=>x.name===t&&x.type==='table'))continue;const cols=await api(target+'/query','PRAGMA table_info('+t+')'),idx=await api(target+'/query','PRAGMA index_list('+t+')'),count=await api(target+'/query','SELECT COUNT(*) AS n FROM '+t);if(count.length!==1||!Number.isSafeInteger(count[0].n))throw Error('GENERALIZED_POST_COUNT_UNKNOWN');n[t]={columns:cols,indexes:idx,row_count:count[0].n};}out.new_details=n;
 const b=await api(target+'/time_travel/bookmark');if(!/^[a-f0-9-]{16,128}$/.test(b.result?.bookmark||''))throw Error('GENERALIZED_POST_BOOKMARK_UNKNOWN');out.bookmark=b.result.bookmark;
 out.preserved=Boolean(out.old_schema_unchanged&&out.old_columns_indexes_unchanged&&out.atomicity_row_unchanged&&out.test_jobs_unchanged&&out.stage2_rows_unchanged&&out.stage2_columns_indexes_unchanged&&out.kv_schema_unchanged);out.classification=classify(schema,n,out.preserved,c);out.pass=out.classification==='FULL_APPLIED';
 }catch{out.failure_code='GENERALIZED_READ_RECONCILIATION_UNCONFIRMED_NO_RETRY';}return out;
}
