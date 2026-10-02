# 非破壊migrationの最終実行承認前gate — 2026-10-03 JST

現在migration0、deploy0、live job0、render0。今回実APIは7回（Write account verify GET1回＋Read認証/inventory/metadata/schema/snapshot/bookmark6回）、remote mutation0。Token値・Token ID・raw responseを記録しない。新しいWriteは登録済みだが実行承認ではない。

## 実測とowner evidence

最終read-only run37061099032、commit1e21c363f51e85cb21eb474b1cb26ecbb01619b9、SUCCESS。隣のsanitized JSONに実証結果を保存。Write Secret存在=true、account-owned GET verify200/active。user endpointへWriteを送っていない。reject/timeout/unknown時のfallback/再送なし。Readは別の既存user-owned Token。

| 項目 | gate結果／証拠 |
|---|---|
| Account | 6c8ccd6aface937ab5dabef61cb64534固定・account verify/D1照会成功 |
| DB ID/名前 | 18050cf6-934e-4f3a-a1cd-5041bac1c35e / plm-serverless-sandbox-state一致 |
| 最新inventory | 全1件、1ページ、other D1=0 |
| schema | test_jobs欠落、job row件数N/A。_cf_KVのみ、同テーブルのdataは読取しない |
| DB size | 12288 bytes、2026-10-02T20:31:24.856Z観測 |
| Time Travel | 新しいbookmark GET200。実restoreは未実施、成功未証明 |
| SQL SHA256 | ac01f6d9d7eac877b802688d4f1d3c4dd40e8940876ed3ce0dc441c10297d0e2 |
| SQL内容 | CREATE TABLE IF NOT EXISTS test_jobs1文のみ、destructive0。変更されたhashは拒否 |
| Free/$0 | PASS、前回本人Dashboard確認。billing API検証とは区別 |
| permission scope | OWNER EVIDENCE。作成画面D1 Write1policy、本人が指定条件で登録完了。APIがscopeを検証したとはしない |
| Write expiry | API観測2026-10-09T23:59:59Z（10/10 08:59:59 JST）。最短custom TTLの証明ではない |
| narrow D1 isolation | SINGLE_TARGET_D1_VERIFIED。全inventoryと固定DBだけの証拠で、Accountの他service用途を証明しない |
| Account isolation Variable | unverified保持。sandbox_only_verifiedへ変更なし |
| execution approval | BLOCKED、本人の別の実行承認が必要。allow false維持 |

scope画面はcreation formであり、作成後policy API readbackではない。この限界をowner evidence JSONに明記。実active Tokenが同じ入力scopeを持つという根拠は本人の指定条件での作成・登録完了の証言。Token管理/Billing/Admin権限を増やして検証しない。

## 準備した一度だけの実行経路

serverless/migration-once.mjsとplm-migration-once.ymlは新しいsandbox専用経路。job if:false、実行許可false、scope/revocation確認未有効。現在pushではSKIP、実Writeは0。既存main setupは変更せず、unverified isolationの拒否も保持。今後の本migrationではAccount全体verifiedを偽装せず、narrow D1 isolationを実Read照会から判定するこの専用経路を使用する。Worker/Admin/deploy経路はない。

実行承認後に、Workがsandbox branchの承認された一回のcommitにだけ経路を束縛する。承認commit SHAを非secret receipt Variableへ登録する準備は済みだが、今は登録・allow変更をしていない。実行時はGITHUB_RUN_ATTEMPT=1、固定repo/branch/push/sha、全4flags trueを要求。GitHub historyの対象workflow/head_sha/event=pushが1runだけ、現在run ID一致、現在branch head一致をReadで確認。unknown/ページ不明/複数run/branch移動はSTOP。共有concurrency groupで旧setupと並行しない。

同processのattemptはRead照会前に消費し、同receiptのconcurrent/replay/resume拒否。GitHub全run rerunはattempt2なので拒否。別runはhistory複数なら拒否。read failureでも自動retryしない。これはD1 durable ledgerのCAS検証とは別であり、GitHub historyをatomic DB予約とは呼ばない。実分散backendのatomicity/競合/restart/replayは将来live readinessのUNVERIFIEDを保持。

実行直前に新しいaccount-owned Write verify、Read全inventory、ID/name、test_jobs欠落、schema、size、bookmark、SQLhashを取り直す。既存test_jobsや他の未知table/D1、名前/ID変更、unexpected rows_written、expiry不明/expired、429/401/403/unknownはSTOP。保存済みbookmarkは今回の証拠であり、将来実行時には再取得する。

全条件が満たされた一回の実行でのみcanonical CREATEをWriteでPOSTする。SQL送信後は再送/自動restart禁止。成功応答後はReadでcanonical schema/columns/row0を検証。失敗・応答不明・post-check不明ならmanual reconciliation。既存schemaに対して再CREATEはしない。

## 失効とrollback

所有者が実行中にCloudflare Token一覧を開ける状態で待機する。成功/失敗/cancel/timeout/unknownの全ケースで、即Cloudflare側revoke/delete→失効確認→GitHub PLM_CF_D1_API_TOKEN削除。7日expiryは保険でありmigration利用期間ではない。登録Secret削除だけではToken失効しない。WorkはToken管理権限を持たず、自動失効済みと報告しない。

Writeが失効するまで別migration/deploy/jobへ進まない。rollbackは停止・4flags保持・Read照合を優先。Time Travel restoreはDB全体上書き、DROP/DELETEも破壊的な別承認事項。CREATEされた空tableを使わず残すことは安全な停止で、DB再作成しない。unknown後にblind retryしない。

## 検証と未達成事項

Python362＋Node91＝453 PASS、FAIL0。native exec/socket guard evidenceでoffline render/external_api_calls0。メモリSQLite＋mockによる、concurrent winner、write適用後応答喪失、rerun、duplicate history、stale branch、unknown history、既存schema拒否を検証。remote SQLは送っていない。実multi-process DB CASをPASSにしない。

offline_complete=true、live_ready=false、posting_permitted=false。進行度約94%（今回+0pt、実migration未実施）、残り6–12h概算＋本人承認と将来24h待ち。100+accountsは別BLOCKER。production/n8n/V1/既存YouTube経路/PR15/16変更なし。

本人に求める次の一操作は、上記対象DB・固定SQLの一回の実行と、実行結果が何であっても直後にToken失効する条件の最終承認。scopeはowner evidenceとして受け入れること、expiry7日を使い切らず直後に失効することを含む。この承認まではどのallow flagも有効化しない。
