// Applies to both Node oracle and in-process Node test suites.
import fs from 'node:fs';
import {syncBuiltinESMExports} from 'node:module';
import {spawnSync} from 'node:child_process';
const probe = spawnSync('/plm-never-execute-probe');
if (probe.error?.code !== 'EPERM') throw new Error('native_exec_guard_required');
for (const key of ['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP']) {
  if (process.env[key] !== 'true') throw new Error('unsafe_flags');
}
const media = /\.(mp4|mkv|mov|avi|webm|wav|mp3|m4a|ass)$/i;
function check(path) {
  if (media.test(String(path))) throw new Error('offline_media_write_denied');
}
for (const name of ['writeFileSync','appendFileSync','createWriteStream','writeFile','appendFile']) {
  const original = fs[name];
  fs[name] = function(path,...args) {check(path);return original.call(this,path,...args);};
}
for (const name of ['writeFile','appendFile']) {
  const original = fs.promises[name];
  fs.promises[name] = function(path,...args) {check(path);return original.call(this,path,...args);};
}
const open = fs.openSync;
fs.openSync = function(path,flags,...args) {
  if (typeof flags === 'number' ? flags & (fs.constants.O_WRONLY|fs.constants.O_RDWR|fs.constants.O_CREAT|fs.constants.O_TRUNC) : /[wax+]/.test(flags)) check(path);
  return open.call(this,path,flags,...args);
};
syncBuiltinESMExports();
// Native LD_PRELOAD seccomp denies ALL socket and exec syscalls irreversibly.

const promisesOpen = fs.promises.open;
fs.promises.open = function(path,flags,...args) {
  if (typeof flags === 'number' ? flags & (fs.constants.O_WRONLY|fs.constants.O_RDWR|fs.constants.O_CREAT|fs.constants.O_TRUNC) : /[wax+]/.test(flags)) check(path);
  return promisesOpen.call(this,path,flags,...args);
};
const callbackOpen = fs.open;
fs.open = function(path,flags,...args) {
  if (typeof flags === 'number' ? flags & (fs.constants.O_WRONLY|fs.constants.O_RDWR|fs.constants.O_CREAT|fs.constants.O_TRUNC) : /[wax+]/.test(flags)) check(path);
  return callbackOpen.call(this,path,flags,...args);
};
syncBuiltinESMExports();
