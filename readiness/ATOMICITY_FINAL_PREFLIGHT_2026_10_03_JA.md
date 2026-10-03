# Atomicity実試験直前のread-only preflight

実試験未承認、mutation0。Token登録はowner evidenceのみ。scope独立検証や管理権限追加をしていない。以前のcleanup/CI/migration/Worker receiptsは変更しない。

preflight run 37100847714、attempt1、SUCCESS。実行code pin `1233ed94342d113571f2cc6a71eab70ae625ac99`、activation `e0ab03f4cb08eb15680785201303e2b45e8bf04b`。checkout HEAD、event before、unique activation message、sandbox repo/branch/attempt1/4flagsを確認。終了後preflight workflowをretireしてif:falseへ戻す。atomicity mutation workflowは一度も有効化していない。

## Remote read証拠

account-owned atomicity Tokenはverify GET1回のみ、200/active、finite expiry `2026-10-10T23:59:59.000Z`（日本時間2026-10-11 08:59:59）。排他permission scopeは本人作成画面のowner evidence、token_scope_api_verified=false。Token ID/raw response/Secretはreceiptに保存しない。

Read Tokenのaudit10回（GET4 + 固定SELECT/PRAGMA POST6）、Write Tokenをaudit envから除去。合計Cloudflare read-only11回、retry/fallback/resend0。inventory全ページtarget1/other0、Account/DB name/ID一致。`backend_probe_v1`15列・constraints・guard1・indexes4 exact、0 rows。`test_jobs`11列/0rows unchanged、`_cf_KV` unchanged、DB40960 bytes、全6query primary=true。

fresh bookmark `0000000c-00000000-000050f9-eda333ceccf63ecca9285718949e58ac`。

schema fingerprint `540a69aa2297b7484138e948cd852f42e2791e3909625d16d3ac24474859e8c3`。

## Plan／history／CI

plan bytes unchanged、SHA `cc4e854c77a5e3115999c7271abeb83974911b353b9afeeab3d8ae08d7d7fb28`。mutation SQL9本、最大成功logical row changes3（initial create/one claim/terminal）、identity1、concurrent contender2（1 runner）、DELETE/retry/resend0。03/04はclient send overlapを実測予定、D1内部並列実行とは扱わない。各SQL/params、期待state/version/owner/fingerprintとprimary rowは既存固定planに従う。最終rowは実15列、ownerはA/B winnerのみ、succeeded/version3、epoch/fence1、last_request_id=terminal、delivery_001/result_001、created=T0/updated=T0+2。

GitHub history GET1page、全1run `37100148817` skipped。prior executionなし。SENT/UNKNOWN/repo test receiptがあれば拒否、history incomplete/unknown/cancelled/crashもfail-closed。artifactをclaim authorityにはしない。

offline CI run37100827057 SUCCESS、Python406/Node291/total697 FAIL0。追加27fixtures。native/seccomp/socket/exec guards維持、offline external_api_calls=0/render_executions=0。

primary row不一致後のreconciliationも最大1setへ補強。timeout/5xx/reset/parse/meta.changes不明/primary不一致で後続停止、同mutation再送禁止。COMMITTED/NOT_COMMITTED/STILL_UNKNOWNを区別し、観測だけでnoncommitを確定しない。no-op unknownはrow不変だけでは判定できずSTILL_UNKNOWN。どの分類でも自動再開せず、still unknownなら終了。unexpected changed no-opは即STOP。固定SQL/plan bytes変更なし。

## 現在の停止点

全体97%（今回+0pt）、残りactive作業概算320–680分。本人待ち・1h/24h観測時間は別。remote schema PASS、bounded plan DESIGN PASS、offline guards PASS、実atomicity/CAS/concurrency/fencing/checkpoint/replayはUNVERIFIED。full backend PASSにしない。Worker deploy/invocation0、live/AI/render/posting0。live_ready=false/posting_permitted=false、4flags=true。100+accountsは別BLOCKER。

次の本人1操作は「最大9 mutation・成功row変更最大3・concurrent contender最大2の固定remote atomicity試験を1回だけ実行」の明示最終承認。Token作成・登録から承認を推測しない。

承認後も送信直前にfinite expiry、最新target-only inventory/schema0row、exact plan/hash/receipt、actual code pin/attempt1/historyを再確認し、不一致/unknownならwriteせずSTOP。token expiredならwrite禁止。実試験成功/失敗/timeout/unknown後に本人がCloudflare Tokenを失効確認しGitHub Secretを削除する。勝手なrollback/DELETE/reset/2回目の試験は禁止。
