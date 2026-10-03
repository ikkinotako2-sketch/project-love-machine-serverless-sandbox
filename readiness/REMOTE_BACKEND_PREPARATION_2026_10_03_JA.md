# 1-account remote D1 atomicity準備 / 2026-10-03

現在97%を維持。今回の進行度+0pt。offline設計は進んだがremote atomicityは未実証。残る実作業は概算330–690分、Token/承認/OAuth/24h metrics等の外部待ちは別。live_ready=false / posting_permitted=false。100+ accountsは別BLOCKER。

## credential cleanupと不変証拠

本人の最新申告に基づき、Worker Editor v2 Token失効/削除、GitHub PLM_CF_WORKER_API_TOKEN削除、D1 Write Tokenなし、D1 Read Token維持をOWNER EVIDENCEとして記録した。API Token管理を追加せず、独立API確認済みとは扱わない。歴史receipt/rollback/failed preflight/成功preflight/CI receiptは編集せず、新しいhash manifestで参照する。

Workerはdeployment a514d0bb-e8e8-4b14-becf-a94ebfb0f92f / version 3f87a1b1-6300-4b69-9b2d-be78346611a0のcanonical stopped状態を維持する。今回はWorker通信・deploy・invocation・flags変更0。D1 binding配置の成功はatomicityの証明ではない。

## 最新read-only audit

run 37093009614 / attempt 1 / commit 60be87996e83bf841a49ca86367b541f91837947がSUCCESS。
2026-10-03T03:23:05.423Z（12:23:05 JST）取得。Read Token active、対象AccountのD1アクセス一致。inventory 1ページで全1件、他D1 0件。

Account 6c8ccd6aface937ab5dabef61cb64534 / DB 18050cf6-934e-4f3a-a1cd-5041bac1c35e / plm-serverless-sandbox-state。
DB size 20,480 bytes。test_jobs 0行。schemaは_cf_KVとtest_jobsのみ（sqlite内部object除外）。既存0001 canonical SQLと11 columns一致。PK index sqlite_autoindex_test_jobs_1の列はplatform/account_id/job_id、unique=1、origin=pk。追加のユーザーindex/triggerなし。

columns: platform TEXT NOT NULL、account_id TEXT NOT NULL、job_id TEXT NOT NULL、content_fingerprint TEXT NOT NULL、claimant TEXT NOT NULL、state TEXT NOT NULL、version INTEGER NOT NULL、last_operation TEXT NOT NULL、run_id TEXT nullable、created_at INTEGER NOT NULL、updated_at INTEGER NOT NULL。
constraints: platform='test'、account_id='test_reference_001'、state IN ready/dispatching/running/succeeded/unknown、version>0、PK(platform,account_id,job_id)。
_cf_KVはkey TEXT PRIMARY KEY/value BLOB、WITHOUT ROWID。既存schemaは変更していない。

Time Travel bookmark取得成功: 00000008-00000000-000050f9-2cb29c01ddd3315759c3856f719068ee。
GET 4 + SELECT/PRAGMA専用query POST 7 =外部API 11。POST 7はread-only SQLで、mutation=0 / D1 write=0。Worker APIは使っていない。
今回の一度限りread workflowは完了後if:falseにretireする。read receipt内migration_required=falseは既存0001の再適用が不要という意味。full backend/probe追加schemaの必要性とは別。
Free/$0は既存本人Dashboard evidenceのPASSを維持。今回Billing API再検証はしていない。PLM_CF_ACCOUNT_ISOLATION=unverifiedを維持。D1 inventory対象1件という狭い証拠からAccount全体sandboxと推論しない。

## current test_jobsとdurable contractのgap

CURRENT SCHEMA SUPPORTSといえるのはcomposite job PKそのものだけ。intent uniqueやCAS全体の保証ではない。以下の分類はschemaだけの評価で、reference成功をremote behavior PASSへ昇格しない。

| 項目 | 分類 | 根拠 | 最初の試験との関係 |
|---|---|---|---|
| unique intent identity | MISSING | intent_idなし。現在PKはplatform/account/jobのみ。 | 第1段階 |
| job_id mint once | PARTIAL | job PKは重複を防ぐが、同一intentに異なるjobをmintできる。 | 第1段階 |
| immutable content fingerprint | PARTIAL | TEXT NOT NULLのみ。変更禁止のDB制約なし。 | 第1段階 |
| version CAS | PARTIAL | version列あり。条件付きUPDATEは可能だが、必須predicateや増加をDBが強制しない。 | 第1段階 |
| owner identity | PARTIAL | claimant列あり。owner不変・有効値・terminal bindingの制約なし。 | 第1段階 |
| owner epoch | MISSING | epoch列なし。第1段階では固定epoch=1のprobeだけ。 | 第1段階 |
| fencing token | MISSING | fencing列なし。handoff/external fencingは第2段階。 | 後続 |
| state transition guard | PARTIAL | 状態enumのみ。遷移順序やfailed terminalは保証されない。 | 第1段階 |
| dispatch reservation | MISSING | dispatching状態名のみで予約ID/一意性/外部副作用の証拠なし。 | 後続 |
| generation checkpoint | MISSING | checkpoint本文/identity/CASなし。 | 後続 |
| checkpoint fingerprint | MISSING | generation内容との固定bindingなし。 | 後続 |
| callback replay/delivery identity | MISSING | delivery id/replay ledgerなし。 | 後続 |
| terminal result uniqueness | PARTIAL | job行PKのみ。result id、delivery id、terminal不変保証なし。 | 第1段階 |
| metrics 1h / 24h uniqueness | NOT REQUIRED FOR FIRST REMOTE TEST | 現在MISSING。metric slot/period uniqueなし。第2段階以降。 | 後続 |
| Improvement uniqueness | NOT REQUIRED FOR FIRST REMOTE TEST | 現在MISSING。improvement checkpoint uniqueなし。 | 後続 |
| next-intent uniqueness | NOT REQUIRED FOR FIRST REMOTE TEST | 現在MISSING。next intent uniqueなし。 | 後続 |
| audit timestamps | PARTIAL | created_at/updated_at列のみ。非回帰/immutable作成時刻/履歴trailなし。 | 第1段階 |
| unknown / ambiguous side effect | PARTIAL | unknown enumあり。mutation attempt/reservation/reconciliation証拠なし。 | 第1段階 |

## 最初のremote実証の最小集合

第1段階はunique intent/job mapping、同version CAS、2 concurrent claim、stale version、stale owner、version 1→2→3、immutable fingerprint、identity/terminal replay no-op、unknown no resend。owner epoch/fencing tokenは固定1のclaim bindingまでであり、handoffや外部副作用fencingを証明しない。

8 contenderはofflineの複数SQLite connection simulatorのみ。remote runnerは2まで。callback duplicate、successful terminal replay、failure replayはofflineで検証。remote第1段階では成功terminal1回だけとし、失敗terminalも同時に作るための別identityは追加しない。

generation checkpoint/durable restart・handoff・本当のcallback authentication/replay ledger・dispatch reservation・metrics/Improvement/next-intentは第2段階以降。probe delivery_id/result_idのunique制約は局所testだけで、production callback ledgerではない。unknownはtransport attempt journalに残し、unknown行追加のためのDB mutationはしない。外部AI/render/投稿副作用は一切なし。

## 最小additive migration

既存test_jobsだけではintent unique/immutable fingerprint/monotonic updateをDB側で強制できず、意味ある第一試験に不足。ALTER案は既存tableの用途と成功証拠を変えるため採用しない。新しい専用backend_probe_v1 + backend_probe_v1_guardを選ぶ。

SQL: serverless/migrations/0002_backend_probe_v1.sql
SHA256: ca2ee1a2c618c5f71b43ade4620d9ded3eb105282be9a610c492632fec59fdc3。
CREATE TABLE 1 / CREATE TRIGGER 1 = DDL 2文。ALTER/DROP/rename/DELETE/standalone INSERT/UPDATE/REPLACE 0。trigger定義内のBEFORE UPDATEは既存データのUPDATE実行ではない。IF NOT EXISTSを使わず、再実行を成功扱いにしない。0001は再実行禁止。

before: _cf_KV、test_jobs canonical 0行、probe table/triggerなし。
after: before不変 + backend_probe_v1（15列、0行） + guard trigger + PK/job/delivery/resultのSQLite auto indexes。probe identityはCHECKで固定1件しか入らない。jobとfingerprintも固定。version/state/owner epoch/fencingを整合CHECK、更新triggerでidentity/fingerprint/作成時刻不変・timestamp非回帰・version+1・ready→claimed→terminalのみを強制する。terminalは更新不可。これはsandbox限定test schemaで、full production durable schemaではない。

将来のmigrationは別本人承認後にSQL fileをD1 RESTへ最大1 HTTP送信（2 DDL文）。REST経路の2文のall-or-nothingは未実証で、binding batchの保証を流用しない。timeout/unknown/partial schemaなら同じmigrationを再送せずread-onlyでtable/trigger/columns/indexes/旧schemaを照合、manual reconciliationでSTOP。

rollback: 自動DROP/DELETE/Time Travel restoreはしない。未使用の空probe構造は停止したまま残せる。Time TravelはDB全体のrestoreであり、別本人承認とfresh inventory/書込停止/新bookmarkが必要。既存bookmarkは取得時点の証拠で、将来の実行直前に再取得必須。Freeは保持7日。復旧成功は未実証。

## D1 / SQLite公式仕様の照合

調査日2026-10-03。次のprimary資料を照合した。

- https://developers.cloudflare.com/d1/worker-api/d1-database/ （2026-06-22更新）: autocommitとbinding db.batchの順次実行・失敗時rollback。今回はWorker/binding APIは使わない。条件付きUPDATE changes=0はSQL失敗ではないためbatch rollback条件にはならない。
- https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/ : REST sql/paramsとmeta。changesはsqlite3_total_changes由来の概算として説明され、rows_writtenはindex分も含む。successful logical row mutation budgetとは区別する。
- https://developers.cloudflare.com/d1/platform/limits/ （2026-04-21更新）: individual databaseはsingle-threadedでqueryを一つずつ処理し、concurrent requestはqueue、過負荷時error。CASの対象rowとpredicateが正しいこと、実際のwinner一人/primary確認は実地試験までUNVERIFIED。
- https://developers.cloudflare.com/d1/best-practices/retry-queries/ （2026-08-10更新）: provider内部のread-only retryが存在する。clientはretryしないが、provider内部実行回数をHTTP送信数から推定しない。文書中のwrite retry例は今回採用しない。
- https://developers.cloudflare.com/d1/best-practices/read-replication/ : read replica/session/bookmarkを区別する。REST meta served_by_primaryはoptional。unknownのcommit確認でprimary性が確認できないread、古いrowやrow不存在はNOT_COMMITTEDの証拠にしない。
- https://developers.cloudflare.com/d1/reference/time-travel/ : bookmarkとDB全体point-in-time restore。取得したbookmarkは復元実施の証拠ではない。
- https://www.sqlite.org/lang_transaction.html / https://www.sqlite.org/isolation.html : local SQLiteのautocommit/single-writer/transaction isolation。reference実装の根拠だけに使い、D1 REST multi-statement atomicityへ一般化しない。

prepared paramsは固定SQLと型の一致で検証。sqlite_total_changes/REST changes単独で勝者としない。future remote read-backではexact identity/fingerprint/version/owner/request IDも照合。HTTP/API timeoutやresponse parse failureはcommit有無を確定できない。

## 固定remote試験plan / write budget

BACKEND_PROBE_FIXED_PLAN_2026_10_03.jsonはfixtureであり実行不可。timestampとwinnerは最終pin前に固定し、winnerは2 claim ACK後のread-backで確定する。planのSQLはINSERT/CLAIM/TERMINALの固定3種のみ、任意SQLを受け付けない。

|順|固定送信|期待するlogical row changes|
|---|---|---|
|1|初期intent INSERT|1|
|2|同identity INSERT replay|0|
|3–4|2 contender同version claimを同時送信|合計1|
|5|winner + stale versionだけ異なるterminal試行|0|
|6|current version + stale ownerだけ異なる試行|0|
|7|current owner/version + wrong fingerprintだけ異なる試行|0|
|8|正しいwinner terminal成功|1|
|9|ACK済terminalの明示的duplicate試験|0|

最大identity1 / mutation SQL HTTP送信9 / 成功logical row変更3 / concurrent runner2。9回はstale version/owner/fingerprintを一つずつ独立検証するための最小構成。旧6送信案ではこれらを混ぜるか省略するため採用しない。09は正常ACK済みの別試験stepでありtimeout後の再送ではない。migrationは別budgetの1HTTP/2DDL。DELETEによる枠再利用なし、terminal rowは監査証拠として残す。

各phaseの前に既存schema/rowをread-backし、非claim stepは順次実行。claim2送信の両ACKとwinner read-backが揃うまでstep5以降を送らない。connection error/401/403/429/5xx/timeout/parse failure/changes不明/期待値不一致でSTOP。provider errorの詳細raw body/credentialは記録しない。

## unknown policy / durable attempt evidence

offline OnceAttemptLedgerは送信前にSENTをfixture journalへ記録し、同request ID/9枠超過を拒否。restart時SENTをUNKNOWNへ昇格。UNKNOWN後は全追加mutationを禁止し、reconciliationでCOMMITTEDと分かっても自動resumeしない。これはmock-only contractであり、remote実試験用のdurable single-run attempt storage/runner crash semanticsがliveで実証済みという意味ではない。

unknown後に新mutationは0。最大1回のread-only reconciliationを許す設計とし、exact primary-confirmed rowに一致する場合COMMITTED、authoritativeな拒否証拠がある場合のみNOT_COMMITTED、それ以外STILL_UNKNOWN。不存在/旧row/replica/無期限in-flightならSTILL_UNKNOWN。どの判定でも同mutationの自動再送なし。unknown時の別endpoint fallbackも禁止。

将来GitHub Actionsのlive executorは新exact approved commit・attempt1・push専用・固定Account/DB・4 flags・inventory全1件・expiry/Token active・schema SHA・history一意・別実行承認を必須とする。今回live executor/workflowは作らず、machine precondition validatorもexecution_permitted=falseを返す。current token欠損状態で通信可能なmutation workflowは今回追加していない。

## 次のowner gate A / Token分離

新migrationが必要。次の本人操作はmigration専用account-owned限定Tokenの作成とGitHub保護登録だけ。
Token名案 plm-sandbox-d1-schema-v2-once / Secret PLM_CF_D1_MIGRATION_V2_TOKEN。
Account D1 Writeのみ、Account 6c8ccd6aface937ab5dabef61cb64534限定、最短有限TTL（選択可能なら24h以下）。Workers/Admin/Billing/Token管理/DNS/Routesなし。単一D1 resource scopeはUNVERIFIEDのため、実行直前inventory全ページ=対象sandbox1件のみを必須にする。Token scopeはowner evidence、API独立scope検証済みとしない。

remote atomicity試験用は後日別Token/Secret PLM_CF_D1_ATOMICITY_TEST_TOKEN。migration用を流用しない。Token登録だけでmigration/試験承認とは扱わず、fresh read-only final gate後に別の1回承認を要求する。migration成功/失敗/timeout/unknownの全結果で即Cloudflare失効確認→GitHub Secret削除を本人が実施。cleanup前に試験へ移らない。Token値はchat/log/commitへ保存禁止。

## readiness

PASS: 現remote test_jobs canonical schema/0行、inventory対象1件、bookmark取得、停止Worker deployの既存証拠。
OWNER EVIDENCE: credential cleanup、Free/$0、Custom Domains/Routesなし。
DESIGN/OFFLINE PASS: additive probe SQL/hash、9-step fixed plan、SQLite競合/replay/unknown simulator、native/socket guards。
UNVERIFIED: remote probe schema、D1 atomicity/CAS/concurrent claim、handoff fencing、generation checkpoint/recovery、callback replay ledger、AI quota実project、実render/投稿。
BLOCKED: migration/remote write承認・限定Tokenなし、TEST_ONLY roundtrip未承認、live_ready=false、posting_permitted=false、100+ accounts別BLOCKER。

今回Cloudflare mutation0 / D1 write0 / Worker deploy0 / invocation0 / live job0 / render0 / SNS/YouTube0。既存migration成功1/再送0、既存stopped deploy成功1を履歴として維持し、今回回数へ混ぜない。

## 最終local CI

Python 400 PASS / Node 188 PASS / 合計588 PASS / FAIL 0。今回追加34 Python + 4 Node = 38 test。native seccomp/socket/exec guardを維持し、guarded CI内external_api_calls=0 / render_executions=0。実D1 read-only auditの11外部APIとは別集計。
