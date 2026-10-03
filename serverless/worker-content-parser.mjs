// Bounded in-memory content/v2 inspection. Never executes or persists provider source.
import {createHash} from 'node:crypto';
export const LIMITS=Object.freeze({total:131072,module:65536,metadata:8192,modules:8,headers:2048});
const JS=new Set(['application/javascript+module','text/javascript+module','application/javascript','text/javascript']);
const TEXT=new Set([...JS,'text/plain','text/html','application/json','application/source-map']);
const BINARY=new Set(['application/wasm','application/octet-stream']);
const TYPES=new Set([...TEXT,...BINARY]);
const NAME=/^[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}$/;
export class ContentError extends Error {constructor(code,diagnostics){super(code);this.code=code;this.diagnostics=structuredClone(diagnostics);}}
const fail=(code,d)=>{throw new ContentError(code,d);};
function name(s,d){if(typeof s!=='string'||!NAME.test(s)||s.includes('..'))fail('MODULE_NAME_UNSAFE',d);return s;}
function utf8(bytes,d){try{return new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);}catch{fail('UTF8_INVALID',d);}}
function hash(bytes,d){try{return createHash('sha256').update(bytes).digest('hex');}catch{fail('HASH_FAILED',d);}}
// Validate duplicate keys at every object depth BEFORE JSON.parse can discard them.
function metadataJSON(bytes,d){
 const s=utf8(bytes,d);let p=0;
 function ws(){while(/[\x20\t\r\n]/.test(s[p]||'!'))p++;}
 function str(){const start=p++;let escape=false;for(;p<s.length;p++){const c=s[p];if(c==='"'&&!escape){p++;const v=JSON.parse(s.slice(start,p));if(/[\uD800-\uDFFF]/u.test(v.replace(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g,'')))fail('METADATA_INVALID',d);return v;}if(c==='\\'&&!escape)escape=true;else escape=false;}throw Error('json');}
 function val(depth=0){if(depth>32)throw Error('json');ws();const c=s[p];if(c==='"'){str();return;}if(c==='{'||c==='['){p++;ws();const end=c==='{'?'}':']',seen=new Set();if(s[p]===end){p++;return;}for(;;){ws();if(c==='{'){if(s[p]!=='"')throw Error('json');const key=str();if(seen.has(key))fail('METADATA_DUPLICATE_KEY',d);seen.add(key);ws();if(s[p++]!==':')throw Error('json');}val(depth+1);ws();if(s[p]===end){p++;return;}if(s[p++]!==',')throw Error('json');}}const m=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(s.slice(p));if(!m)throw Error('json');p+=m[0].length;}
 try{val();ws();if(p!==s.length)throw Error('json');const obj=JSON.parse(s);if(!obj||Array.isArray(obj)||typeof obj!=='object')throw Error('json');return obj;}catch(e){if(e instanceof ContentError)throw e;fail('METADATA_INVALID',d);}
}
function mime(s){return typeof s==='string'?s.split(';',1)[0].trim().toLowerCase():'';}
export async function readBoundedContent(response,diagnostics){
 const type=mime(response.headers.get('content-type'));
 diagnostics.content_type_family=type==='multipart/form-data'?'MULTIPART_FORM_DATA':JS.has(type)?'JAVASCRIPT':type==='text/plain'?'TEXT_PLAIN':'UNSUPPORTED';
 let count=0,chunks=[];
 try{if(!response.body)fail('BODY_MISSING',diagnostics);const reader=response.body.getReader();for(;;){const {done,value}=await reader.read();if(done)break;count+=value.byteLength;diagnostics.bounded_total_bytes=Math.min(count,LIMITS.total);if(count>LIMITS.total){await reader.cancel().catch(()=>{});fail('BODY_TOO_LARGE',diagnostics);}chunks.push(value);}return Buffer.concat(chunks,count);}catch(e){if(e instanceof ContentError)throw e;fail('BODY_READ_FAILED',diagnostics);}
}
export function parseWorkerContent(input,headers,diagnostics={}){
 const bytes=Buffer.from(input);diagnostics.bounded_total_bytes=Math.min(bytes.length,LIMITS.total);diagnostics.parts=[];
 if(bytes.length>LIMITS.total)fail('BODY_TOO_LARGE',diagnostics);
 const rawType=headers.get('content-type')||'',type=mime(rawType);
 diagnostics.content_type_family=type==='multipart/form-data'?'MULTIPART_FORM_DATA':JS.has(type)?'JAVASCRIPT':type==='text/plain'?'TEXT_PLAIN':'UNSUPPORTED';
 const headerEntry=headers.get('cf-entrypoint'); // Official Wrangler GET response selector; no heuristic fallback.
 if(headerEntry!==null)name(headerEntry,diagnostics);
 let modules=[],metadata=null,metadataCount=0,selector=null;
 if(JS.has(type)){
  if(bytes.length>LIMITS.module)fail('MODULE_TOO_LARGE',diagnostics);utf8(bytes,diagnostics);
  modules=[{name:headerEntry??'raw-body.js',content_type:type,byte_size:bytes.length,sha256:hash(bytes,diagnostics)}];
  selector=headerEntry??'raw-body.js';diagnostics.entrypoint_source=headerEntry?'CF_ENTRYPOINT':'RAW_JS_BODY';diagnostics.raw_body_name_is_synthetic=headerEntry===null;
 }else if(type==='multipart/form-data'){
  const boundary=/^multipart\/form-data\s*;\s*boundary=(?:"([A-Za-z0-9'()+_,./:=?-]{1,70})"|([A-Za-z0-9'()+_,./:=?-]{1,70}))\s*$/i.exec(rawType);
  if(!boundary)fail('MULTIPART_PARSE_FAILED',diagnostics);
  const marker=Buffer.from('--'+(boundary[1]||boundary[2])),sep=Buffer.from('\r\n'+marker);let pos=0;const names=new Set();
  if(!bytes.subarray(0,marker.length).equals(marker))fail('MULTIPART_PARSE_FAILED',diagnostics);pos=marker.length;
  for(;;){
   if(bytes.subarray(pos,pos+2).toString('ascii')==='--'){pos+=2;if(pos===bytes.length||bytes.subarray(pos).equals(Buffer.from('\r\n')))break;fail('MULTIPART_PARSE_FAILED',diagnostics);}
   if(!bytes.subarray(pos,pos+2).equals(Buffer.from('\r\n')))fail('MULTIPART_PARSE_FAILED',diagnostics);pos+=2;
   const endHeaders=bytes.indexOf(Buffer.from('\r\n\r\n'),pos);if(endHeaders<0||endHeaders-pos>LIMITS.headers)fail('MULTIPART_PARSE_FAILED',diagnostics);
   const headerBytes=bytes.subarray(pos,endHeaders);if([...headerBytes].some(x=>x<32&&x!==13&&x!==10||x>126))fail('MULTIPART_PARSE_FAILED',diagnostics);
   const h={};for(const line of headerBytes.toString('ascii').split('\r\n')){const m=/^([A-Za-z-]+):[ \t]*(.*)$/.exec(line);if(!m||Object.hasOwn(h,m[1].toLowerCase()))fail('MULTIPART_PARSE_FAILED',diagnostics);h[m[1].toLowerCase()]=m[2];}
   if(h['content-transfer-encoding'])fail('MODULE_TRANSFER_ENCODING_UNSUPPORTED',diagnostics);
   const cd=/^form-data;\s*name="([^"\r\n]*)"(?:;\s*filename="([^"\r\n]*)")?$/i.exec(h['content-disposition']||'');if(!cd)fail('MULTIPART_PARSE_FAILED',diagnostics);
   const partName=name(cd[1],diagnostics);if(cd[2]!==undefined&&name(cd[2],diagnostics)!==partName)fail('MODULE_FILENAME_MISMATCH',diagnostics);
   const end=bytes.indexOf(sep,endHeaders+4);if(end<0)fail('MULTIPART_PARSE_FAILED',diagnostics);
   const body=bytes.subarray(endHeaders+4,end),mt=mime(h['content-type']||'text/plain');pos=end+sep.length;
   diagnostics.part_count=(diagnostics.part_count||0)+1;
   if(partName==='metadata'&&++metadataCount>1)fail('METADATA_DUPLICATE',diagnostics);
   if(names.has(partName))fail('DUPLICATE_PART_NAME',diagnostics);names.add(partName);
   diagnostics.parts.push({name:partName,content_type:TYPES.has(mt)?mt:'UNSUPPORTED',byte_size:body.length});
   if(partName==='metadata'){
    if(body.length>LIMITS.metadata)fail('METADATA_TOO_LARGE',diagnostics);
    if(!['application/json','text/plain'].includes(mt))fail('METADATA_TYPE_UNSUPPORTED',diagnostics);
    metadata=metadataJSON(body,diagnostics);continue;
   }
   if(modules.length>=LIMITS.modules)fail('MODULE_COUNT_LIMIT',diagnostics);
   if(body.length>LIMITS.module)fail('MODULE_TOO_LARGE',diagnostics);
   if(!TYPES.has(mt))fail('MODULE_TYPE_UNSUPPORTED',diagnostics);
   if(TEXT.has(mt))utf8(body,diagnostics); // Binary modules are hashed without JS/text decoding.
   modules.push({name:partName,content_type:mt,byte_size:body.length,sha256:hash(body,diagnostics)});
  }
  if(metadata){
   const keys=['main_module','body_part'].filter(k=>Object.hasOwn(metadata,k));
   if(keys.length!==1)fail(keys.length?'MAIN_MODULE_AMBIGUOUS':'MAIN_MODULE_MISSING',diagnostics);
   selector=name(metadata[keys[0]],diagnostics);diagnostics.entrypoint_source=keys[0].toUpperCase();
   if(headerEntry!==null&&headerEntry!==selector)fail('ENTRYPOINT_CONFLICT',diagnostics);
  }else{if(headerEntry===null)fail('METADATA_MISSING',diagnostics);selector=headerEntry;diagnostics.entrypoint_source='CF_ENTRYPOINT';}
 }else fail('CONTENT_TYPE_UNSUPPORTED',diagnostics);
 diagnostics.selected_main_module=selector;
 const selected=modules.filter(x=>x.name===selector);if(selected.length!==1)fail(selected.length?'MAIN_MODULE_DUPLICATE':'MAIN_MODULE_NOT_FOUND',diagnostics);
 if(!JS.has(selected[0].content_type))fail('MAIN_MODULE_TYPE_UNSUPPORTED',diagnostics);
 diagnostics.module_count=modules.length;
 return {module_count:modules.length,modules:modules.sort((a,b)=>a.name.localeCompare(b.name,'en')),main_module_name:selector,main_module_sha256:selected[0].sha256,entrypoint_source:diagnostics.entrypoint_source,raw_body_name_is_synthetic:diagnostics.raw_body_name_is_synthetic===true};
}
