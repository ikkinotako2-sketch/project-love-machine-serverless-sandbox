# 非破壊migrationの実行準備 — 2026-10-03 JST

今回は準備承認のみ。migration、deploy、live job、Cloudflare変更、実Cloudflare API呼出しは全て0。offline_complete=true、live_ready=false、posting_permitted=false、安全フラグ4件true。main/production/n8n/V1/既存YouTube経路/PR15/16は変更しない。100+accountsは別BLOCKER。

## 修正と検証

sandbox branchのcloudflare-setup.mjsでuser-owned/account-ownedのverify URLを明示選択。Read/Write/Workerは独立したowner種別、未指定/不正値はHTTP前に拒否。401/403/429/5xx/unknown/timeoutで再送や別endpoint fallbackを行わない。固定Account UUIDも追加。raw response、provider error、Token ID/valueは出力しない。SQLをSHA256固定し変更を拒否。workflowのmigration実行許可はfalse固定。mockのmigration試験はメモリSQLiteのみで、実migrationではない。

Python362＋Node67＝429 PASS、FAIL0。初回ローカル起動は安全フラグを付け忘れguardがexit90で拒否（テスト未実行、外部呼出しなし）。4flagsを全trueで明示した再検証が全PASS。main既存workflowは未修正。修正後の実Token roundtripは未実施。

## 実行直前に必須の確認表

| 項目 | 固定値／必要な証拠 | 現在 |
|---|---|---|
| Account ID | 6c8ccd6aface937ab5dabef61cb64534 | 固定、前回D1アクセス確認 |
| DB ID | 18050cf6-934e-4f3a-a1cd-5041bac1c35e | 固定、前回一致 |
| DB名 | plm-serverless-sandbox-state | 固定、前回一致 |
| SQL SHA256 | ac01f6d9d7eac877b802688d4f1d3c4dd40e8940876ed3ce0dc441c10297d0e2 | 現ファイル一致、runtime照合 |
| destructive SQL | 0件、CREATE TABLE IF NOT EXISTS test_jobsのみ1文 | 内容/SQLitefixture確認 |
| inventory | 全ページで対象1件のみ、実行前に新鮮な照会証拠 | 前回run37056753511／1ページ1件を保存。今の証拠とは混同しない |
| Free/$0 | 指定AccountのWorkers Free表示＋D1使用量画面 | UNVERIFIED |
| Write scope | Account→D1→Writeだけ、Include Specific Account＝上記Account | 未作成。verify成功ではscope検証できない |
| isolation | 所有者のAccount用途確認、保護対象不存在 | unverified維持。自動verified禁止 |
| execution approval | 条件確認後の別の明示実行承認 | 未承認。workflow false固定 |
| backup | 直前の対象schema/row状態、Account/DB照合、Time Travel/backup可否確認 | 未実施。12KiBの前回サイズはbackupではない |

## Free/$0を確認する本人操作（まずこれだけ）

Cloudflare Dashboardで指定Accountを選び、Workers & Pagesのプラン表示（Workers Free）とD1使用量（読み書き・storage、更新日時）を確認できる画面を提示する。Account対応が分かるようにする。ドメインのFree表示だけではWorkers/D1のFree証明にならない。Tokenやカード情報を表示しない。Upgradeやカード登録は不要／禁止。Work側にはbilling証拠・権限がなく、前回Cloudflareブラウザのsecurity challengeも未解除なのでUNVERIFIEDを維持。新しいbilling TokenやAdminを要求しない。

## その確認後に使うWrite Tokenの最小手順（今回は作成要求しない）

所有者がCloudflareのCustom API TokenでAccount→D1→Writeのみを選ぶ。他のpermission、All Accounts、Worker/Admin、Token managementを含めない。Account resourceは上記1件だけ。D1 WriteはAccount全D1への権限であり、このDB1件へのprovider側制限とは呼ばない。本番D1の存在/用途不明なら発行禁止。owner種別、permission/resource summary、expiryをToken値を隠して確認。migration専用名と最短TTLを付け、実行時刻直前に発行。UIが短期TTLを設定できない場合は停止し、継続承認を取り直す。

GitHub sandboxだけの保護入力欄にPLM_CF_D1_API_TOKENを登録。値はchat/workflow input/file/logに出さない。非secret Write owner variableは別に明示。Read Tokenはそのまま保持。実行前に所有者が失効操作をできる状態で待機し、許可されたworkflowを1回だけ動かす。

## 完了／中断直後の失効

成功、失敗、cancel、timeout、応答不明のどれでも、所有者がCloudflareの当該Tokenを即revoke/deleteし、Token一覧で失効を確認。その後GitHub sandboxのPLM_CF_D1_API_TOKEN Secretを削除。Secret削除だけではCloudflare Tokenは失効しない。TTLは保険であり即失効の代替ではない。WorkへToken管理/Admin権限を追加して自動失効する設計は採用しない。Secret値ではなく完了時刻・失効確認結果だけを記録する。

## backup／rollback／unknown

直前read-onlyでschema/rowsを記録し、backup/Time Travelの使用可否を確認するまで実行しない。test_jobs欠落が現状態なら同テーブルの既存dataはないが、DB全体が空とは断定しない。他テーブルは変更しない。CREATE成功後の安全な停止は4flagsを保持して新テーブルを使わず残す。自動DROP/DELETE/restoreは行わず、必要時は別のdestructive承認。unknown/timeoutならまずTokenを失効し、Readでschemaを照合しmanual reconciliationにする。再CREATE、再dispatch、DB再作成は禁止。

公式照合資料（2026-10-03確認）：
- https://developers.cloudflare.com/api/resources/user/subresources/tokens/methods/verify/
- https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/verify/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/fundamentals/api/get-started/create-token/

Free tierの公開上限はAccountの実plan証拠とは別。Freeで上限超過時queryが拒否される仕様を公式pricingで確認したが、対象AccountがFreeとは断定しない。
