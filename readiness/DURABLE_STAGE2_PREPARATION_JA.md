# Durable backend stage2 準備（2026-10-03）

全体98%、今回+0pt、残り実作業300–660分（計画見積り、認証・quota待機と1h/24h待機を除く）。live_ready=false / posting_permitted=false、4安全flag=true。

cleanupはowner evidenceのみ。Token管理APIによる独立検証なし。read-only audit run37104775137 PASS、GET4+読み取りSQL POST7=11、mutation/write0。inventory対象1件・他0、size40960 bytes、bookmark0000000e-00000000-000050f9-e9101970abd8137fa72777040e62336a。旧probe成功row1件/succeeded/version3/contender_a、test_jobs0行、schema/trigger/index一致。_cf_KVはschema一致であり、内容を独立検証したとは扱わない。

## 既存remote PASSとgap

run37101718265の固定probe範囲でunique intent/mint once、identity replay、initial CAS、same-version競合、stale version/owner拒否、fingerprint条件不一致拒否、terminal replay no-op、version1→2→3を保持。再試験/reset禁止。full production backend PASSではない。

20項目の個別分類はDURABLE_STAGE2_READINESS_2026_10_03.jsonへ固定。arbitrary overwrite、callback delivery/result、restart SENT/UNKNOWNはPARTIAL（旧probe列/guardまたはrunner履歴拒否のみ）。handoff/epoch/fencing/checkpoint/dispatch/ambiguous state/callback ledger等は現在remote MISSING。metrics1h/24h、Improvement、next-intentの実測は最初の単発roundtrip前不要だが、継続自動化前は必須。candidate offline DESIGN PASSをremote PASSへ昇格しない。

## 非破壊migration

既存table extensionと専用tableを比較し、固定namespace/CHECKと成功rowを持つ旧probeを変更しない専用3tableを採用。durable_stage2_job16列、checkpoint11列、callback9列、trigger6、autoindex8。before旧4schema object/成功row exact、after旧4unchanged+新9object、新table空。

0003_durable_stage2_probe.sql raw SHA256:
`012eae70985512f4672546e8f773ed43392754fc95149192b4b0108daf836686`

CREATE TABLE3+CREATE TRIGGER6=トップレベル9文。DROP/DELETE/ALTER/rename=0、トップレベルDML=0、旧table変更0、0001/0002再実行0。新callback trigger本文に新job UPDATE1文を含むがmigration中には実行されない。IF NOT EXISTSによる再送不可。

rollbackは自動DROP/reset/restoreなし。追加物を凍結して残し、部分作成/UNKNOWNはread-only reconciliation。Time TravelはDB全体を戻し旧監査rowを失う可能性があり別本人承認が必要。fresh前bookmarkと利用期限は実行時確認。REST multi-DDL atomicityはUNVERIFIEDで、SQLite/Worker binding batchから一般化しない。

## Contract

Handoffは旧owner停止証拠＋in-flight NONEが必要。timeoutのみは禁止、STARTED/UNKNOWN checkpoint中は禁止。A→Bでepoch/fence/version+1、旧owner/token0 change、duplicate0。public synthetic proofは実owner停止証拠ではない。remote fencing PASSは新ownerのみ進行し旧owner/tokenがprimary rowを変更しない実測まで保留。

Checkpointはjob/intent/input fingerprint/request contractへimmutable binding、STARTED1→COMPLETED2、output fingerprint/ref保持。completed再生成禁止、STARTED/UNKNOWN自動生成再開禁止。crash前未commitは予約作成だけ、possible commitはread-only照合。fixture://stage2/generation.jsonは公開fixtureでありproduction成果物保存ではない。実AI前にnormalized outputのdurable保存/hash/ref可用性が必須。欠損/破損STOP、再生成なし。

Callbackはdelivery PK、job/account/epoch/fence/payload/result binding。first consumeとterminal更新を同一INSERTのtrigger内で処理、exact duplicate no-op、異なるpayload/identity拒否。HMAC実認証/外部callback未実施。SQLite rollbackでは両変更が戻るが実D1 triggerとaffected countはUNVERIFIED。

Side effect reservation→SENT→UNKNOWN。timeout/応答消失時再送禁止。read-only reconciliation最大1セット。COMMITTEDでも自動resume禁止、NOT_COMMITTED再送も別本人承認、STILL_UNKNOWNはSTOP。fixture状態遷移を実provider回復証拠としない。

## 次remote test（未承認・未実行）

plan raw SHA256:
`230c1acee56c3be8a68cac3c29341675a67cc43d926f2047926982510fdc65b7`

固定SQL/params/完全before-after rowはJSONに保存。1job/1checkpoint/1callback、14mutation sends、9logical changes、runner1、DELETE/retry/resend0。前回9操作を再実行しない。

01job create、02handoff、03stale owner0、04stale fence0、05duplicate0、06checkpoint STARTED、07COMPLETED、08duplicate0、09reserve、10SENT（外部通信なし）、11UNKNOWN、12stale callback0、13consume+terminal（2logical changes）、14duplicate0。

final job owner_b/epoch2/fence2/version6/SUCCEEDED/CONFIRMED、checkpoint COMPLETED/version2、callback1件。時刻T0からT0+7。handoff競合はoffline2 SQLite接続で検証、remote runner1で前回claim競合を重複しない。実provider、複数callback競合、arbitrary overwrite remote ABORTは本plan外。

stage3 workflowはhard-disabled、allow=false、approved commit UNAPPROVED、CLI preflight only。migration helperはfresh確認後最大1HTTP送信＋read-only post-check。Secret登録だけでは動かない。実行entryのrun履歴全ページ/永続SENT journal/承認activationは実行前必須gateとして残す。現時点でlive execution経路完成とは扱わない。snapshot/schema drift/401/403/429/unknownならSTOP、retry/fallbackなし。

## YouTube接続条件

| 時点 | 必須条件 |
|---|---|
| 実AI前 | exact project/model/free quota、限定credential、明示承認、durable checkpoint、normalized output保存/fingerprint/ref、UNKNOWN no-regeneration |
| 実render前 | checkpoint可読、input/artifact fingerprint、$0容量/quota、安全sandbox経路、本人承認 |
| private upload前 | exact OAuth account/限定scope/本人同意、private ONLY（unlisted別承認）、durable upload intent/reservation、SENT/UNKNOWN no-resend、provider read-only reconciliation、asyncならcallback auth/consume ledger |
| 単発中 | stable owner、epoch/fence binding、unknown停止。owner固定ならhandoff運用延期可、timeout takeover禁止 |
| upload後 | 1h/24h実metrics、slot uniqueness、Improvement、next-intent uniqueness。継続job開始前に検証 |

4flag解除/Worker変更は別承認。Worker停止凍結、deploy/invocation/AI/render/upload/posting0。100+ accounts別BLOCKER。

## 次の本人操作

account-owned `plm-sandbox-d1-stage3-schema-once` を作成し、sandbox GitHub Secret `PLM_CF_D1_STAGE3_MIGRATION_TOKEN` に保護登録。Account→D1 Edit/Writeのみ、exact Account6c8ccd6aface937ab5dabef61cb64534、有限の短いTTL、Workers/Admin/Billing/Token管理/DNS/Routesなし。値をchat/log/artifactへ出さない。単一DB scope未確認のためfresh inventory対象1件必須。登録はmigration承認ではない。future test Secret PLM_CF_D1_STAGE2_TEST_TOKENは別用途、今は作成しない。migration後は結果を問わず本人がCloudflare失効＋GitHub Secret削除。

## 公式資料と保証の境界

- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://developers.cloudflare.com/d1/sql-api/foreign-keys/
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://www.sqlite.org/lang_createtrigger.html

D1のSQLite conventionとWorker binding batch仕様はREST multi-DDL保証そのものではない。trigger/RAISEのreference検証と実D1検証を分ける。affected count欠損はUNKNOWN、primary readbackなしにPASSへ上げない。
