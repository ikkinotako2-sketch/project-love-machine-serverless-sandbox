import {candidate} from './generalized-backend-contract.mjs';
import {ACCOUNT,DB} from './atomicity-schema-audit.mjs';
import {uploadURL} from './stage3-file-import-contract.mjs';
import {boundedDiagnostic} from './safe-cloudflare-errors.mjs';
export async function importFixed(e,f,{journal,post}={}){
 const c=candidate(),endpoint=`https://api.cloudflare.com/client/v4/accounts/${ACCOUNT}/d1/database/${DB}/import`,out={status:'BLOCKED',classification:'STILL_UNKNOWN',side_effect_http:0,poll:0,import_http:0,steps:[],post_sets:0,retry:0,resend:0,fallback:0,automatic_rollback:0,query_mutations:0};let possiblySent=false;const used=new Set();
 async function send(a,fields){const poll=a==='poll';if(out.import_http>=6||(poll?out.poll>=3:used.has(a)||out.side_effect_http>=3))throw Error('GENERALIZED_IMPORT_BUDGET');if(poll)out.poll++;else{journal.reserve(a,{status:'SENT',hashes:c.hashes});used.add(a);out.side_effect_http++;possiblySent=true;}out.import_http++;
 const r=await f(endpoint,{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{Authorization:`Bearer ${e.PLM_CF_D1_ROUNDTRIP_BACKEND_TOKEN}`,'Content-Type':'application/json'},body:JSON.stringify({action:a,...fields})});const {body,audit}=await boundedDiagnostic(r);out.steps.push({operation:a,...audit});const s=body?.result;if(!r.ok||body?.success!==true||!s||typeof s!=='object'||Array.isArray(s)||s.success===false||s.error!==undefined||(s.status!==undefined&&!['complete','error'].includes(s.status)))throw Error('GENERALIZED_IMPORT_RESPONSE_UNKNOWN');
 if(s.upload_url!==undefined){if(a!=='init'||s.status!==undefined||s.at_bookmark!==undefined||s.result!==undefined||typeof s.upload_url!=='string'||typeof s.filename!=='string')throw Error('GENERALIZED_IMPORT_CONFLICTING_STATE');}
 else if(s.status==='complete'){if(s.result?.num_queries!==16)throw Error('GENERALIZED_IMPORT_COMPLETE_UNEXPECTED');}
 else if(s.status==='error')throw Error('GENERALIZED_IMPORT_PROVIDER_ERROR');
 else if(!/^[a-f0-9-]{16,128}$/.test(s.at_bookmark||''))throw Error('GENERALIZED_IMPORT_STATE_UNKNOWN');
 return s;}
 try{if(!journal||!post||!e.PLM_CF_D1_ROUNDTRIP_BACKEND_TOKEN)throw Error('GENERALIZED_IMPORT_GATE_MISSING');let state=await send('init',{etag:c.plan.sql_md5});
 if(state.upload_url!==undefined){const u=uploadURL(state.upload_url),name=state.filename;if(name.length>256||!/^[A-Za-z0-9_.-]+$/.test(name))throw Error('GENERALIZED_IMPORT_FILENAME_UNKNOWN');if(out.side_effect_http>=3||out.import_http>=6||used.has('upload'))throw Error('GENERALIZED_IMPORT_UPLOAD_BUDGET');journal.reserve('upload',{status:'SENT',hashes:c.hashes});used.add('upload');out.side_effect_http++;out.import_http++;const r=await f(u,{method:'PUT',redirect:'error',signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/sql'},body:Buffer.from(c.sql)});out.steps.push({operation:'upload',http_status:r.status});if(r.status!==200||r.headers.get('etag')?.replace(/^"|"$/g,'')!==c.plan.sql_md5)throw Error('GENERALIZED_IMPORT_UPLOAD_UNKNOWN');state=await send('ingest',{filename:name,etag:c.plan.sql_md5});}
 while(state.status!=='complete'&&out.poll<3)state=await send('poll',{current_bookmark:state.at_bookmark});
 out.status=state.status==='complete'?'ACK_NEEDS_POST':'STOP';if(out.status==='STOP')out.failure_code='GENERALIZED_IMPORT_POLL_EXHAUSTED';
 }catch{out.status=possiblySent?'STOP':'BLOCKED';out.failure_code='GENERALIZED_IMPORT_STOP_NO_RESEND';}
 if(possiblySent){out.post_sets=1;try{out.post=await post();out.classification=out.post.classification||'STILL_UNKNOWN';if(out.status==='ACK_NEEDS_POST'&&out.post.pass&&out.classification==='FULL_APPLIED')out.status='SUCCESS';else out.status='STOP';}catch{out.status='STOP';out.failure_code='GENERALIZED_POST_UNKNOWN_NO_RETRY';}out.manual_reconciliation_required=out.status!=='SUCCESS';}return out;
}
