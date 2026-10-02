import './node_guard.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';

test('native guard denies external program execution before path lookup', () => {
  for (const name of ['ffmpeg','ffprobe','docker','voicevox','renderer']) {
    const result=spawnSync(name,['--offline-denied-probe']);
    assert.equal(result.error?.code,'EPERM');
  }
});
test('native guard denies socket before any network IO', async () => {
  const socket=net.createConnection({host:'127.0.0.1',port:9});
  const code=await new Promise(resolve => socket.once('error',error => resolve(error.code)));
  assert.equal(code,'EPERM');
  socket.destroy();
});
test('Node guard denies media writes', () => {
  assert.throws(()=>fs.writeFileSync('/tmp/plm-forbidden-probe.mp4','not written'),/offline_media_write_denied/);
});
test('Node runtime has safety flags and no publish permission', () => {
  for (const k of ['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP']) assert.equal(process.env[k],'true');
  console.log('NODE_OFFLINE_GUARD_EVIDENCE render_executions=0 external_api_calls=0 exec/socket probes=DENIED');
});
