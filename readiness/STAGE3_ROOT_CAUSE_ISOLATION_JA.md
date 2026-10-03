# Stage3 HTTP400 root-cause isolation / 新import候補

## 結論と確度

cleanupはowner evidence。旧recovery Token/GitHub Secret失効削除、Read Tokenのみ維持。Token管理API追加なし。今回Cloudflare API=0、remote D1 mutation/write=0。
旧run37108371746/37114446310とSENT/UNKNOWN receiptは不変。双方の現在適用状態はNOT_APPLIEDとして別read-only証拠あり。現在remoteを追加auditしていないためlatest known bookmarkは00000013-00000002-000050f9-60af1b067a4fa57a9ab11628d526ae73。

|候補|確度|根拠・限界|
|REQUEST_FORMAT|低：仕様違反は否定|2026-10-03公式HTTP schemaは{sql,params}と{batch:[{sql,params}]}の両方を定義。SDK表示にはbatch露出差があるが実HTTP schemaを優先。実装が同schemaを満たす保証ではない。|
|SPEC_IMPLEMENTATION_MISMATCH|中|documented valid2形式がHTTP400。local D1で9DDL成功。ただしprovider code未保存、runtime時期差あり。|
|PARTICULAR_DDL|低・remote未除外|9DDLのexact request bytesはSQLiteとlocal D1個別全PASS。構文だけの個別失敗なし。|
|TRIGGER_PARSER|有力・中〜高、未確定|公式Wrangler current source execute.ts自身が/queryのsemicolon分割とcompound CREATE TRIGGER/CRLF問題に言及。triggerには内部semicolonがあり、9要素batchでも各sqlのserver parserは残る。旧候補はLFなのでCRLF固有原因とは断定できない。|
|OTHER|低〜不明|scopeはowner evidence、verify active。authorization・remote version・API validation等はerrors codeがないため完全排除しない。|

HTTP400のerrors[].code/messageは保存されていない。旧logs/receiptから復元したという主張はしない。今後は16KiB bounded JSON reader、最大4errors、numeric code、固定語彙の最大160文字safe messageだけを記録。不明messageはREDACTED。Token/raw headers/raw body/signed URL/opaque filename/provider logsは保存しない。

## 個別DDL実行

|順|object|SQLite|local D1|
|1|durable_stage2_job|PASS|PASS|
|2|durable_stage2_checkpoint|PASS|PASS|
|3|durable_stage2_callback|PASS|PASS|
|4|durable_stage2_job_guard|PASS|PASS|
|5|durable_stage2_checkpoint_insert_guard|PASS|PASS|
|6|durable_stage2_checkpoint_guard|PASS|PASS|
|7|durable_stage2_callback_insert_guard|PASS|PASS|
|8|durable_stage2_callback_immutable|PASS|PASS|
|9|durable_stage2_callback_apply|PASS|PASS|

request SQL文字列の各SHAを記録し、SQLite execute / local D1 prepare().run()を1DDLずつ実行。batch一括実行の成功で個別PASSを代用していない。
Miniflare5.20260801.0-alpha/workerd1.20260801.1（既存installed）、supported compatibility date2026-08-08。2026-10-01はlocal binaryが拒否。remote Workerのcompatibility dateを変更していない。
local runtimeにcredentialを渡さず、LD_PRELOAD connect/bind/sendtoをloopback/Unix限定。local binding RPC用loopback通信あり、外向き接続なし。Cloudflare API0 / targetWorker invocation0。通常CIのnative/seccomp/socket/exec guardは変更しない。

6triggerはSQLite/local D1で構文を受理。WHEN subquery、RAISE、複数body statements、changes()/CASEに個別parse failureなし。安全guardを削ってDDLを単純化する変更は行わない。最小化すべき対象はSQL安全条件ではなく/query transport parserの経由。

## transport比較（今回未実行）

|方式|side-effect送信|partial/unknown|retry・logs|採否|
|REST /query 1DDLずつ|最大9POST|途中停止でtable/triggerの一部を残す。compound trigger parserは依然通る。|自作ならretry0可能。ただし9回の失敗面。|不採用|
|official Wrangler d1 execute --remote --file|通常init POST・signed PUT・ingest POST＋poll POST。cached initは自身でingest開始可能。|file import失敗時原状態復帰の公式説明あり。今回実証は未済。|4.119.0のD1 fetch call pathでmutation再送loopを確認していない。ただしpoll recursionは上限なし・raw provider logsあり。全Wrangler操作にretry0と一般化しない。|直接CLIは不採用|
|official REST SQL-file /import、bounded専用wrapper|side-effect最大3（init1/upload1/ingest1）、read-only poll最大3、import経路HTTP合計最大6|同じ公式file import経路。partialなら削除せずSTOP。|全side-effect SENT先行、no retry/resend/fallback。pollも最大3。raw logsなし。|唯一の選択|
|wrangler migrations apply|migration管理tableへの書込み等が追加|公式rollback説明あり。過去migration列挙/管理状態とprobe試験を混ぜる。|今回追加objects/HTTP回数を最小に固定しにくい。|不採用|

/importは/query compound splitterを通さないofficial file import経路。remoteでの成功/rollback atomicityはUNVERIFIEDのまま。
initはupload URLがなくてもcached fileのingestionを開始し得る。したがってinitをread-onlyとして数えず最初にSENTを保存。upload URLはmemoryのみ、HTTPS/R2 allowlist、redirect禁止、Authorizationを渡さない。ETagをMD5一致検証するがartifact identityはSHA256固定。

## exact候補と次工程

0005_durable_stage2_file_import.sqlは新file・新SHA。0004の9DDLのSQL bytesをそのまま各singlelineに並べ、新transport識別commentだけ追加。logical schema/constraintsは弱めない。3TABLE/6TRIGGER/top-levelCREATE9、DROP/DELETE/ALTER/rename/既存変更0。
SQL SHA=c01e08915c97aaf457879aa163dcd0e02faabab36a7ef044c3e5acaca2d1c23f。
plan SHA=32e1d91c2907fd70bdd0a0d5e6379c7f24af9d04906ad8a265cce951aa694b14。

固定順序：fresh auth/inventory/schema/NOT_APPLIED/hash/history → exclusive SENT init → init1 → upload-requiredならSENT upload/PUT1/ETag検証/SENT ingest/ingest1 → status poll0〜3 → Read Token post-check1セット。
各timeout/5xx/reset/parse failure/403/400/unknownで後続side-effect停止。同操作の再送・新run自動resumeなし。init応答が失われた場合でもpost-check以外のingest/pollを推測実行しない。
post期待：3tables6triggers/16・11・9columns/8autoindexes/0newrows/既存成功row・schema・test_jobs不変/whole inventory/fresh bookmark。
HTTP import status complete + num_queries9 + post FULL_APPLIED exactでのみSUCCESS。その他manual reconciliation。partialをDROP/DELETE/ALTER/Time Travel restoreで自動修正しない。
rollback/restoreは別本人承認。期待index/schemaは固定local生成のstage3-recovery-expected-schemaと一致するsingleline SQL。

新workflow plm-stage3-file-import-once.ymlはhard-disabled/allowfalse。live CLIなし。今後credential登録後はverify/ReadToken audit/exact pin/prior-receipt hash/履歴全ページ/durable journalを結線した専用entryをoffline検証し、実import直前で再び本人最終承認へ戻る。
新Token予定名plm-sandbox-d1-stage3-import-once、Secret PLM_CF_D1_STAGE3_IMPORT_TOKEN。account-owned/Account D1 Edit Writeのみ/exact Account/短いfinite TTL、Workers/Admin/Billing/Token管理/DNS/Routesなし。Account全D1に届くため直前inventory1件・他0が必須。registration≠executionapproval。実行後全結果で即owner cleanup。

進行度概算98%（+0pt）。remote stage2・AI/render/YouTube/1h24h/Improvementは未実施。live_ready=false/posting_permitted=false/4flags true/100+accounts別BLOCKER。

## 公式照合（2026-10-03）
- https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
- https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/import/
- https://developers.cloudflare.com/d1/tutorials/import-to-d1-with-rest-api/
- https://developers.cloudflare.com/d1/get-started/
- https://developers.cloudflare.com/workers/wrangler/commands/d1/
- https://github.com/cloudflare/workers-sdk/blob/main/packages/wrangler/src/d1/execute.ts
