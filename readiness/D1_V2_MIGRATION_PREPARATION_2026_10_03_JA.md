# D1 schema v2 / 最終migration準備

対象はsandbox branch plm-offline-readiness-v1-20261002のみ。現在97%、今回+0pt。残り実作業概算330–690分（外部待ちは別）。登録済Tokenはowner evidence、migration実行承認ではない。token_scope_api_verified=falseを維持。4 flags=true、live_ready=false、posting_permitted=false。

## 固定候補

Account 6c8ccd6aface937ab5dabef61cb64534 / DB 18050cf6-934e-4f3a-a1cd-5041bac1c35e / plm-serverless-sandbox-state。
0002_backend_probe_v1.sqlのraw bytesを再照合した。
SHA256 ca2ee1a2c618c5f71b43ade4620d9ded3eb105282be9a610c492632fec59fdc3。
CREATE TABLE 1 / CREATE TRIGGER 1、DROP/DELETE/destructive ALTER/rename/既存test_jobs変更/0001再実行は0。
SQLの文字・空白1 byteでも変化したら拒否。SQLは今回変更していない。

## 今回のread-only preflight

新workflow PLM D1 V2 Final Read Only Preflightはexact sandbox repo/branch、本人提示head 75113cc2e7d08cd708b1fe4399cc66c463cfb5c1をparentとする1回のprepared push、固定commit message、attempt1を要求。checkoutはそのexact push SHA。read-only認可とmigration認可を分離。
Account-owned migration Tokenはaccount verify GETのみ。user endpoint fallbackなし、401/403/404/429/timeout/parse failureで停止。activeとexpires_onの有限未来時刻を必須とする。Token ID/値/raw responseを出力しない。
D1 inventory/schema/columns/indexes/0行/size/bookmarkはRead Tokenだけで読む。Write TokenはRead検査へ渡さない。
_cf_KV/test_jobs以外の非内部schema object、probe table/trigger存在、旧schema/columns/index変化、size変化、他D1等でSTOPする。直前audit 37093009614との比較。PLM_CF_ACCOUNT_ISOLATION=unverifiedのまま。inventory対象D1一件という限定証拠からAccount全体sandboxとは推論しない。
正常時12 HTTP = GET5 + SELECT/PRAGMA query POST7、全read-only。Worker API/invocationなし。provider内部read retry回数とHTTP送信回数を区別する。

## one-shot workflow / 実行禁止

plm-d1-v2-migration-once.ymlはif:falseでhard-disabled。ALLOW default false、approved commit/owner approval/receipt SHAはUNAPPROVED。Secret登録ではpush/dispatch/mutationされない。実行時は別本人承認後のexact approved commit、attempt1、SQL SHA、Account/DB/4 flagsを要求する。
entryは承認前にHTTPしない。承認済preflight receipt hashが不一致・不足なら停止。GitHub workflow history全ページを読む設計で、自run以外の過去non-skipped run（success/failure/cancelled/unknown）を拒否。concurrency groupは既存sandbox setupと共通。exclusive local SENT intentをPUTではなくD1 query POSTの直前に作成。最大mutation HTTP1。再送・fallback・自動rollback0。
SQLite referenceの成功をD1 transaction成功に昇格しない。REST multi-statementの原子性はUNVERIFIED。2DDLの部分適用もunknown/manual reconciliationとして扱う。

## 固定post-check

serverless/d1-v2-expected-post.jsonにLOCAL SQLite fixtureとしてschema/columns/indexesを固定。expectedではbackend_probe_v1 table1、15 columns、guard trigger1、auto indexes4、0行。旧_cf_KV/test_jobs schema・11 columns・0行は不変、inventory対象1件不変、新bookmark取得を要求する。
HTTP成功+post-check全PASSのみSUCCESS。HTTP応答なし/5xx/parse failureはschemaが一致してもUNKNOWNのまま。post-checkはRead Tokenによる最大8 HTTP（GET2/query POST6）の照合一式を一度だけ。schema不一致や読取応答不明では途中STOPし、同じreadも自動再実行しない。
remote probe row INSERT/CAS/claim/stale owner/fingerprint試験は一切含めない。remote-test credentialは別Secret PLM_CF_D1_ATOMICITY_TEST_TOKENで将来別承認。Workerは凍結したまま。

## 失効 / rollback

migration実行結果SUCCESS/FAILURE/TIMEOUT/UNKNOWNのすべてで、直後に本人へCloudflare migration Token失効確認→GitHub PLM_CF_D1_MIGRATION_V2_TOKEN削除を要求して停止する。owner失効を推測しない。
既存_cf_KV/test_jobsに触れない。自動DROP/DELETE/Time Travel restoreなし。partial/unknownはread-only reconciliation後STOP。Time Travel restoreはDB全体の変更のため別本人承認。実行直前のfresh bookmarkが必須。

## offline検証

Python402 + Node212 = 614 PASS、FAIL0（local）。今回追加Node24。wrong context/pin/flags、missing credential、401/403/404/429、expiry、他D1、旧schema変化、probe存在、journal競合、1回mutation、unknown後read-only、post mismatch、workflow disabled、history拒否をfixtureで検証。公開fixture文字列は実認証ではない。native/socket/exec guardを維持し、CI内external_api_calls=0/render_executions=0。

新read-only snapshotとGitHub CI結果は後続のimmutable audit-evidence receiptへ保存する。歴史receiptは変更しない。production/sandbox main/n8n/V1/既存YouTube/1h/24h/Improvement/PR15/16に変更なし。100+ accounts別BLOCKER。

## remote最終preflight結果

run 37095359659 / attempt1 / commit ff1b4430dbe6dabc4fcc6dd5c38b4ccfb4f52363 SUCCESS。Token account-owned verify200/active、expiry 2026-10-10T23:59:59.000Z（2026-10-11 08:59:59 JST）。正確なpermission scopeはowner evidenceのまま、token_scope_api_verified=false。
D1 inventory全1ページ/対象1件/他0件、Account/DB ID/DB名一致。旧schema・columns/indexesは前snapshot一致、test_jobs0行、probe table/triggerなし、size20,480 bytes。
最新bookmark 00000009-00000000-000050f9-5f43b47f7fae7c09d98477ebc55fb0f7。read schema完了時刻 2026-10-03T04:05:55.218Z。
GET5 + read-only query POST7 = HTTP12、mutation/D1 write/deploy/invocation/live job/render/posting0。
固定receipt SHA256 13ae44a8499700f5f7f06925d893b79ca56ac8c58fa0a4b54fa49db24378aa0b。今回read-only workflowはif:falseにretireし、追加通信なし。migration workflowは引き続きhard-disabled、ALLOW default false、approved commit/owner approval UNAPPROVED。
本当に次の本人操作は、この固定SQLの1回migration実行承認だけ。承認が来ても直前のfresh token/inventory/schema/bookmark再確認に不一致やunknownがあれば書き込まず停止する。成功/失敗/timeout/unknownのどの場合も直後のToken失効・GitHub Secret削除を本人へ要求して停止する。
