// Offline decoder candidate only. Never installed in the consumed v1 runner.
import {readFileSync} from 'node:fs';import {sha} from './atomicity-schema-audit.mjs';import {jsonBounded} from './d1-v2-migration.mjs';
const raw=readFileSync(new URL('./migrations/0007_generalized_roundtrip_backend.sql',import.meta.url));
if(sha(raw)!=='45f042a1342676ceeeed587490d80eb132e31a2c3d9b33cceeab3045ffdf37b5')throw Error('RT_V2_MIGRATED_SQL_DRIFT');
export const TRIGGER_TOKENS=Object.freeze([...new Set([...raw.toString().matchAll(/RAISE\(ABORT,'(rt_[a-z0-9_]+)'\)/g)].map(m=>m[1]))]);
const allowed=new Set(TRIGGER_TOKENS);
export function extractSafeTrigger(message){
 if(typeof message!=='string')return {token:null,reason:'MESSAGE_NOT_STRING'};
 if(message.length>160)return {token:null,reason:'OVERSIZED'};
 if(/[^\x20-\x7e]/.test(message))return {token:null,reason:'CONTROL_OR_NON_ASCII'};
 const words=[...message.matchAll(/[A-Za-z0-9_]+/g)].map(m=>m[0]),candidates=words.filter(w=>w.includes('rt_'));
 if(candidates.length!==1)return {token:null,reason:candidates.length?'MULTIPLE_TRIGGER_TOKENS':'NO_TRIGGER_TOKEN'};
 const token=candidates[0];if(!allowed.has(token))return {token:null,reason:'SUBSTRING_OR_UNKNOWN_TRIGGER'};
 // Extract exactly one full identifier, then require an error-cause wrapper.
 // Merely mentioning a token, a SQL literal, or an unrelated error is not proof.
 const replaced=message.replace(token,'TRIGGER');
 const wrapper=/^(?:(?:D1_ERROR|D1_EXEC_ERROR): )?(?:Error (?:in (?:line|statement) [1-9][0-9]{0,5}|at offset [0-9]{1,6}): )?(?:(?:SQL execution error|SQL error|sql error|query error|SQLITE_CONSTRAINT_TRIGGER): )?TRIGGER(?:: SQLITE_CONSTRAINT(?:_TRIGGER)?)?$/;
 if(!wrapper.test(replaced))return {token:null,reason:'UNSUPPORTED_OR_UNRELATED_WRAPPER'};
 return {token,reason:'UNIQUE_ALLOWLISTED_TRIGGER_CAUSE'};
}
export async function decodeExpectedRejectionV2(response,expectedToken){
 const out={match:false,logical_changes:null,safe_trigger_token:null,diagnostics:[]};let b;
 try{b=await jsonBounded(response,16384);}catch{return {...out,reason:'BOUNDED_RESPONSE_UNCONFIRMED'};}
 const errors=Array.isArray(b?.errors)?b.errors:[];
 out.diagnostics=errors.slice(0,4).map(e=>({code:Number.isSafeInteger(e?.code)?e.code:null,safe_message:extractSafeTrigger(e?.message).token||'[REDACTED_UNRECOGNIZED_MESSAGE]'}));
 if(!allowed.has(expectedToken)||![200,400].includes(response.status)||b.success!==false||errors.length!==1||errors[0].code!==7500||!(b.result===undefined||b.result===null||Array.isArray(b.result)&&b.result.length===0))return {...out,reason:'UNEXPECTED_ERROR_ENVELOPE'};
 const extracted=extractSafeTrigger(errors[0].message);if(extracted.token!==expectedToken)return {...out,reason:extracted.token?'WRONG_EXPECTED_TRIGGER':extracted.reason};
 return {...out,match:true,logical_changes:0,safe_trigger_token:extracted.token,reason:extracted.reason};
}
