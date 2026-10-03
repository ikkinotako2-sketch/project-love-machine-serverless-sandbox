# 1-account sandbox atomicity実地試験の最終準備

97%は作業進捗の概算。今回+0pt。remote behaviorを実証していないため進捗を水増ししない。残り実作業320–680分、外部待ちは本人認証・承認および将来の1h/24h観測で別枠。

## cleanupと最新remote audit

schema v2 migration Token失効/削除、GitHub migration Secret削除、Worker Editorなしは本人owner evidence。Token管理API確認ではない。Read Tokenのみ維持、atomicity Write Token未作成。広い管理権限を追加していない。

read-only run 37099745940、attempt=1、commit 23ffd93b5690a7ff933a903ffc893b823e7e36c3。成功1回、rerunなし。GET4 + read SQL POST6 = Cloudflare read-only 10回。D1 mutation/write=0。対象AccountにD1は全1件、他0。Account全体sandbox isolationはunverifiedのまま、D1 inventory対象1件のみの狭い証拠を用いる。

DB `plm-serverless-sandbox-state` / `18050cf6-934e-4f3a-a1cd-5041bac1c35e`、size=40960 bytes。`backend_probe_v1` 15列、guard trigger1、unique indexes4、probe0行。`test_jobs`11列/0行、`_cf_KV`を含む既存schema unchanged。6 read queryのprimary attribution=true。

bookmark: `0000000b-00000002-000050f9-66845e0ce976f6c0028cff0854145cb7`。

schema fingerprint: `540a69aa2297b7484138e948cd852f42e2791e3909625d16d3ac24474859e8c3`。

migration receipt run37098401244 SHA: `2310028cfcc6a7222411a059fe9d62f2f5a847fbaabbeaaa1a73ef47c4263e22`。既存receiptを変更せず新しいaudit receiptを追加。

## 固定planと最小budget

plan raw-file SHA256: `cc4e854c77a5e3115999c7271abeb83974911b353b9afeeab3d8ae08d7d7fb28`。

| sequence | mutation | expected logical changes | resulting version |
|---|---|---:|---:|
| 01 | fixed identity INSERT | 1 | 1 |
| 02 | same identity INSERT replay | 0 | 1 |
| 03+04 | A/B same-version claim, concurrent HTTP | sum=1 | 2 |
| 05 | stale version terminal attempt | 0 | 2 |
| 06 | stale owner terminal attempt | 0 | 2 |
| 07 | wrong fingerprint terminal attempt | 0 | 2 |
| 08 | canonical terminalization | 1 | 3 |
| 09 | identical terminal replay | 0 | 3 |

mutation SQL送信最大9、identity最大1、successful logical row changes最大3（create/claim/terminal）、concurrent client contenders最大2、hosted runner1、DELETE/retry/resend0。独立した拒否・replayと2送信競合を残すため9未満へ削減しない。SQL batchへまとめてHTTP数だけ少なく見せない。physical rows_writtenはindex更新等と区別し、3をphysical storage writesの意味で使わない。

exact SQL/params/expected before/after/version/owner/fingerprintとSTOP条件は`serverless/atomicity-test-plan.json`に固定。実行中にSQLを追加しない。identityはplatform=test/account=test_reference_001/intent=plm-d1-atomicity-20261003-r1/job=plm-d1-atomicity-job-001。production IDsを使用しない。rowは監査として残し、DELETE/resetしない。

T0は実行開始時秒を一度capture、T1=T0+1、T2=T0+2の論理試験timestamp。HTTP実時刻は別receipt欄。最終rowはplan内実15列のみ、state=succeeded/version=3/owner=AまたはB/epoch=fence=1/last_request_id=terminal/delivery_001/result_001。created=T0/updated=T2。勝者は2応答sum1とprimary readの双方で確定し、その他branchはない。

07はfingerprintをWHERE条件にbindした拒否の実証対象。DB guardによるFP上書き拒否はschemaおよびoffline SQLiteで確認するが、最初のremote試験で上書き攻撃を送ったとは扱わない。full production immutable fingerprintやcallback ledgerのPASSには昇格しない。

## 公式仕様照合（2026-10-03取得）

- https://developers.cloudflare.com/d1/platform/limits/ — 個別DBはsingle-threaded、queryは1つずつ、同時requestはqueueされ得る。2 client HTTP期間のoverlapとsingle winnerを記録する。serverが2 SQLを並列実行したとの証明にはしない。
- https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/ — REST query params、results、optional meta.changes/served_by_primary。changesは概数の表現であり、単独で強い証明とせずexact primary rowと併用。field不明ならSTOP。
- https://developers.cloudflare.com/d1/worker-api/return-object/ — changesとrows_written/total_attemptsを区別。Binding APIからRESTへの保証の自動一般化はしない。
- https://developers.cloudflare.com/d1/worker-api/d1-database/ — binding batchのautocommit/sequential/transaction rollback仕様。今回REST単文CASでありbatchを使わない。
- https://developers.cloudflare.com/d1/sql-api/sql-statements/ — PK/UNIQUE/CHECK/UPDATE条件付きSQL。SQLite referenceだけでD1 atomicityをPASSにしない。

## unknownとrestart

HTTP timeout/5xx/reset/parse failure/affected count不明でSENT→UNKNOWN、後続mutation停止、既に送った同時2本だけsettleまで待つ。Read Tokenの固定SELECTによるreconciliation最大1セット。exact primary rowからそのmutationのcommitを確認できればCOMMITTED、確実な拒否ACKがあればNOT_COMMITTED、観測だけで否定できなければSTILL_UNKNOWN。no-opのtimeoutはrow不変からcommit有無を区別できずSTILL_UNKNOWN。どの分類でも自動resume/resendしない。still unknownなら終了。unexpected changesは実数を隠さずSTOP。

SENT journalをexclusive create + fsyncしてからsend。SENT/UNKNOWNが残るpathでrestart禁止。runner filesystem消失をartifact lockで解決しない。全pageのActions historyで過去non-skipped runがある場合はcancel/crash/receipt不存在でも拒否。歴史がunknown/incompleteなら拒否。repoの過去test receiptも拒否条件。artifactは小さい監査journalのみ1日保持、authority/claimには使わない。

## 実行入口（現在hard-disabled）

workflow `plm-d1-atomicity-test-once.yml` はif:false、allow=false、owner approval/checkout commit pin=UNAPPROVED。Secret追加だけでは実行しない。将来別承認後のみexact tested commitをpinし、attempt1、repo/branch/account/DB/4flags/planSHA/schemaFP/migrationreceiptSHA/actual checkoutを確認。old migration/Worker credentialを渡さない。account-owned verifyにfallbackなし、finite expiry必須。実行直前fresh target-only inventory/schema0row/primary read gate必須。

Workerはcanonical stoppedのまま、deploy/invocation/vars/DB access変更0。remote testはActions→D1 APIだけ。fencing handoff/generation checkpoint/real callback replay ledger/metrics/Improvement/next-intentは除外しUNVERIFIED。live_ready=false/posting_permitted=false。

## 次の本人操作（Token登録と実行承認は別）

限定Token `plm-sandbox-d1-atomicity-test-once` をaccount-owned、Account D1 Write/Editのみ、exact Account `6c8ccd6aface937ab5dabef61cb64534`、finite/short TTLで作成し、GitHub保護Secret `PLM_CF_D1_ATOMICITY_TEST_TOKEN` へ登録する。Workers/Admin/Billing/Token管理/DNS/Routesなし。単一DB resource排他scopeはAPI検証済みと呼ばず、実行直前にAccount内D1が対象1件のみ再確認。migration用Token/Secretは再利用しない。値はchat/log/commitへ出さない。

登録後も実試験は別の本人承認まで禁止。成功/失敗/timeout/unknown後、本人がCloudflare Token失効確認とGitHub Secret削除。自動rollbackなし。100+accountsは別BLOCKER。
