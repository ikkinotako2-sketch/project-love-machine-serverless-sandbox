// PUBLIC SYNTHETIC FIXTURES ONLY. Not captured Cloudflare responses.
export function multipartFixture(parts,{entry=null,boundary='PLM_SYNTHETIC_BOUNDARY'}={}){
 const chunks=[];
 for(const p of parts){
  const filename=p.filename===false?'':`; filename="${p.filename??p.name}"`;
  chunks.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="${p.name}"${filename}\r\nContent-Type: ${p.type??'application/javascript+module'}\r\n\r\n`));
  chunks.push(Buffer.isBuffer(p.body)?p.body:Buffer.from(p.body??''));chunks.push(Buffer.from('\r\n'));
 }
 chunks.push(Buffer.from(`--${boundary}--\r\n`));
 const headers=new Headers({'content-type':`multipart/form-data; boundary=${boundary}`});if(entry!==null)headers.set('cf-entrypoint',entry);
 return {bytes:Buffer.concat(chunks),headers};
}
export function metadataFixture(obj){return {name:'metadata',filename:false,type:'application/json',body:typeof obj==='string'?obj:JSON.stringify(obj)};}
export function playgroundLikeFixture(code){return multipartFixture([
 metadataFixture({main_module:'index.js',bindings:[{type:'secret_text',name:'PUBLIC_FIXTURE_SECRET_NAME',text:'PRIVATE_FIXTURE_VALUE_NEVER_SAVE'}]}),
 {name:'index.js',body:code},
 {name:'data.js',body:'export const data = {fixture:true};'},
 {name:'welcome.html',type:'text/plain',body:'<h1>PUBLIC SYNTHETIC PLAYGROUND-LIKE FIXTURE</h1>'}
 ]);}
