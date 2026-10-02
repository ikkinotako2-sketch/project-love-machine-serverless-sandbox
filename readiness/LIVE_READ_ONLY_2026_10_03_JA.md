# live read-only検証 — 2026-10-03 JST

offline_complete=true、live_ready=false、posting_permitted=falseを維持。

## 実ログで確認した原因

main inspect #1 / run37055519676 はAccount IDとDatabase IDが空。実コードはHTTP前にinvalid_account_idで拒否する。Read Secretはmaskedで存在し、Write/Worker credentialは空。推測でTokenを変更せず、sandboxのVariables3件をユーザー指定値で登録した。isolationはunverifiedのまま。

main inspect #2 / run37056233774 はmain/inspectで今回1回だけ実行しFAIL。Variablesは正しく注入されていたが、既存CLIは一律SETUP_BLOCKEDのため詳細原因を隠していた。mainコード/既存workflowは変更していない。

sandbox branchだけにread-only診断を追加。run37056753511 / commit dd55af3f1fdd7cc60024bfc3f29338daab6c6ed8 はSUCCESS。実API証拠は隣のJSON。account-owned verifyは401/code1000、別user-owned verifyは200/active。登録Tokenはuser-owned型であり、既存setupがaccount-owned endpointを固定使用していることと非互換。Token値・Token ID・rawエラーメッセージ・rawレスポンスは保存していない。この分類はこのTokenへのRead照会証拠で、全Token権限が最小と検証できた意味ではない。

## 確認結果

| 項目 | 結果 |
|---|---|
| Account | 6c8ccd6aface937ab5dabef61cb64534 に対するD1照会成功。別Accountへ照会なし |
| auth | user-owned Token active。main inspectのaccount-owned verifyは401 |
| 全D1 inventory | total_count=1、1ページ、列挙1件、同Account内の他D1は0件 |
| 対象DB | ID18050cf6-934e-4f3a-a1cd-5041bac1c35e、名前plm-serverless-sandbox-state一致 |
| 用途 | 既存指定ID/名前との照合のみ。Account全体の用途・本番共有不存在の証明とはしない |
| size | API metadata file_size=12288 bytes（12KiB）。請求全体の使用量ではない |
| schema | sqlite_masterの固定SELECTでtest_jobsは0件＝テーブルなし |
| test_jobs row件数 | テーブルがないのでN/A。COUNT=0を捏造しない |
| schema mismatch | テーブル欠落。存在するテーブルのconstraints検証は未実施 |
| migration | test_jobs準備には必要。今回未実行。1-accountの本番durable ledgerとは別 |
| Worker | 固定Worker settingsへのGETは403。存在/不存在はUNVERIFIED。Admin/Editorを追加しない |
| Free/$0 | 現TokenのD1 Read証拠だけではplan/billing/共有usageを確認できずUNVERIFIED |
| account_isolation | unverifiedを保持 |

段階1の認証と指定AccountのD1 access、段階2inventory/ID/name、段階3schemaの有無読取を完了。段階4はmigration承認とWrite credentialが必要。Worker存在・Free/billing・実backendatomicity/restart/replayは未完了。Cloudflare readiness全体をPASSへ上げない。

## 安全性・数値

Cloudflare mutation0、migration0、deploy0、live job0、render0。診断の実Cloudflare API呼出し6回。新main inspectはaccount verifyで停止する既存コード順と診断の401証拠から1回の実API attemptと推定されるが既存runはcounterを出さないため測定値と混同しない。今回既知の実API attemptは合計7（診断6測定＋inspect1推定）。前runはVariables未入力でHTTP前に停止。

公開モデル・fixtureとは分離して記録。offline guardCIのexternal_api_calls=0/render_executions=0は引き続き正しいが、このターンの実Cloudflare read6回を0とは報告しない。

新規Node fixture tests16件。CI run37056753488でPython362/Node57、合計419 PASS/FAIL0。実diagnosticは同じendpoint再送を行わず、確定4xxのaccount verify後にだけ異なるuser verifyを1回実行した。timeout/unknown/429/5xxでfallback・retryしない。schema SELECT/PRAGMAの固定allowlist以外のPOSTは拒否。Writer/Admin/外部job/rendererへの経路なし。

診断workflowのlive credential実行は完了したcommit dd55af3に固定し、以後のpushでは実照会しない。新しい実照会には別の明示的な作業指示が必要。isolationをverifiedへ変更しない。既存main inspectは非互換が残るため、同じmain runを盲目的に再実行しない。

進行度は約93%（前92から+1pt、計画上の概算）。残り6–12時間はremotebackend実装/障害検証次第で増加。外部承認待ち未定、将来70分/24h待ちは別計上。100+accountsは別BLOCKER。

次の本人承認候補は、この既存sandbox D1へのchecked-in 0001_test_jobs.sqlの非破壊migration。承認だけでWrite発行を許可済みとせず、Account用途/Free/$0と最小Write scope・短期失効方法が確認できるまで実行しない。本番D1共有Write、destructive DDL、Admin、Emergency Stop解除、TEST_ONLY実往復、AI/render/private投稿は含めない。
