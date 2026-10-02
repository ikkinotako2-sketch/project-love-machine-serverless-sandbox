# 最新migration前read-only証拠 — 2026-10-03 05:15 JST

Run37059375077 / commit3adaef22c65f1abadce9a2c6051e773a9380daa9 SUCCESS。今回指示に基づき一度だけ実照会、user-owned verify200/active。API6回、mutation0、migration0、deploy0、live job0、render0。Secret/Token値・provider raw responseは保存しない。current_schemaはDBデータのbackupではなくschema定義だけ。

| gate | 最新結果 |
|---|---|
| Free/$0 | PASS（本人Dashboard確認、2026-10-03 05:13 JST）。Workers Free active、支払方法なし。別JSONへ出典を保存 |
| auth | PASS user-owned verify、account-owned endpointへ送信なし、fallback/再送なし |
| inventory | PASS 全1件、1ページ、other D1=0 |
| Account | 6c8ccd6aface937ab5dabef61cb64534への実D1照会成功 |
| DB | 18050cf6-934e-4f3a-a1cd-5041bac1c35e / plm-serverless-sandbox-state一致 |
| test_jobs | MISSING、row count N/A、migration必要 |
| current schema | _cf_KVテーブル1件の定義。データ内容は読取・保存しない。Dashboardの利用者向けテーブル0表示と生schemaの1件を区別 |
| size | metadata12288 bytes。本人Dashboard12.29KB表示。表記差を統一せず出典ごと保存 |
| SQL | SHA256 ac01f6d9d7eac877b802688d4f1d3c4dd40e8940876ed3ce0dc441c10297d0e2一致、固定CREATE IF NOT EXISTS1文、destructive0 |
| Time Travel | GET bookmark200、bookmark取得成功。schemaと同じ証拠JSONへ保存 |
| isolation | unverified維持。D1 inventoryだけでAccount全体用途をverifiedにしない |
| Write scope | UNVERIFIED、未登録。active verifyはscopeの証明ではない |
| execution | BLOCKED、workflow実行許可false、準備承認のみ |

診断のfree_plan=UNVERIFIEDはbilling権限で検証していないAPI観測を表す。これを上書きせず、別のowner-confirmed Free/$0 PASS証拠と合成する。過去のFree未確認記録は歴史として保持する。

Time Travelは公式に常時有効、Freeでは7日。GET bookmarkはD1 Read対応。今回の取得は現在の復元点の存在証拠であり、実restore成功の証明ではない。restoreはDB全体を上書きする破壊的操作なので、今回のCREATE準備承認に含めない。rollbackは4flags保持→Token即失効→Read照合→manual reconciliation。自動DROP/restore/再CREATE禁止。将来migration実行直前にbookmark/schema/inventoryの鮮度を再確認する。

## 次の本人操作はWrite Token作成・保護登録だけ

CloudflareでCustom API Token `plm-sandbox-d1-migrate-once` を作成。permissionはAccount→D1→Writeだけ、resourceはInclude→Specific Account→6c8ccd6aface937ab5dabef61cb64534の1件。Workers/Admin/Billing/Token管理/All Accountsは禁止。D1 WriteはAccount全D1へのpermissionであり1DB専用scopeと呼ばない。migration専用、UIで設定できる最短の期限にする。Token種別/permission/resource/expiryは値を隠したsummaryで最終確認が必要。

GitHubのproject-love-machine-serverless-sandbox Repository Secret `PLM_CF_D1_API_TOKEN` の保護入力欄へ登録。値はchat/log/commitへ出さず、完了だけ通知。Token作成または登録はmigration実行承認ではない。mainの既存コードは未変更、sandbox修正版の安全な実行経路も最終承認前にreviewする。Write登録を検知した自動workflowは追加しない。

成功/失敗/cancel/timeout/unknownのいずれでもCloudflare側で即revoke/delete、失効確認後GitHub Write Secret削除。Secret削除だけでは失効しない。WorkへToken管理/Admin権限を与えない。実行時は所有者が失効操作可能な状態で待機する。unknown時は盲目的再送禁止。

offline再検証はPython362＋Node71＝433 PASS、FAIL0。外部socket/exec拒否guardを維持。前回追加のuser-owned Write fixtureもPASS。実Writeは行っていない。実診断workflowは今回commitに固定し後続pushでSKIP。

公式照合：
- https://developers.cloudflare.com/api/resources/d1/subresources/database/subresources/time_travel/methods/get_bookmark/
- https://developers.cloudflare.com/d1/reference/time-travel/
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/d1/platform/pricing/

進行度約94%（前93から+1pt、概算）、残り実作業6–12h＋本人承認/将来24h待ち。offline_complete=true/live_ready=false/posting_permitted=false、安全4flags true。100+accountsは別BLOCKER。production/n8n/V1/既存YouTube経路/PR15/16に変更なし。
