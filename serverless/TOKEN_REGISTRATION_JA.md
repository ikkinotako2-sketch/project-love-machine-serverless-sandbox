# Cloudflare account-owned Token登録手順 — sandbox専用

2026-10-02。設定値は確定。CloudflareのToken作成画面はWorkから開けないため、現行画面の細かな欄名・配置は未検証。下記権限・scopeを選べない場合は停止し、別権限で代用しない。

## 対象と入力値

保存済みD1作成画像のURL/DB欄で確認した非Secret識別子:

- Cloudflare Account ID: `6c8ccd6aface937ab5dabef61cb64534`
- D1 name: `plm-serverless-sandbox-state`
- D1 ID: `18050cf6-934e-4f3a-a1cd-5041bac1c35e`
- Worker: `plm-serverless-sandbox-control`（存在は未確認）
- GitHub: `ikkinotako2-sketch/project-love-machine-serverless-sandbox`

| 項目 | D1用 | Worker用 |
| --- | --- | --- |
| Token名 | `plm-sandbox-d1-setup` | `plm-sandbox-worker-deploy` |
| Token方式 | account-owned | account-owned |
| 必要権限 | `D1 Write`：固定migrationとschema読み取り | Workersの`Editor`：既存Worker更新・deploy/binding |
| Account scope | 上記Account IDだけ | 上記Account IDだけ |
| Resource scope | D1のaccount scope。単一DB限定は公式資料から保証できない | Individual Workers / `plm-serverless-sandbox-control`のみ |
| GitHub Actions Secret | `PLM_CF_D1_API_TOKEN` | `PLM_CF_WORKER_API_TOKEN` |
| 有効期限 | 作成日から7日後（UTC、今回のsandbox検証用） | 同左 |
| Client IP制限 | 未設定（GitHub hosted runnerは固定単一IPではない） | 同左 |

今回は追加のD1 Read Tokenを作らず、migrationに必要なWrite Tokenでinspectも行う。inspectだけならReadが最小だが、Write工程に進めない。Token更新/失効管理は長期運用設計に別途必要。

D1 Writeは対象accountの他DBにも権限が及ぶ可能性がある。コードは確定DB ID・名前を照合するが、provider側の単一DB隔離ではない。このaccountに保護すべき本番D1がありaccount-wide権限を許容できない場合は発行を停止。Worker Admin、全Workers、全Accounts、Zone/DNS/Routes、Billing、API Token Provisioning権限をこれらCI Tokenへ追加しない。

## Cloudflare: 同じログイン中に2つのTokenを作成

1. Cloudflareへ本人がログインし、上記Account IDのアカウントを選ぶ。
2. 左メニュー `Manage account` → `Account API tokens` → `Create Token`。
   個人プロフィールのAPI TokensやGlobal API Keyのページではない。
3. Token名へ `plm-sandbox-d1-setup` を入力。
4. 権限は `D1 Write` のみ。対象accountは上記IDだけ。全accountを選択しない。
5. 有効期限を作成日の7日後に指定。追加権限・IP条件は追加しない。
6. `Continue to summary`。名前・D1 Write・対象account・期限を照合。
7. `Create Token`。表示された値はスクリーンショットやチャットへ送らず、次のGitHub Secret欄へ直接コピーする。
8. 同じ `Account API tokens` へ戻り `Create Token`。
9. Token名へ `plm-sandbox-worker-deploy` を入力。
10. Workers権限は `Editor`、scopeは個別Worker、選択は `plm-serverless-sandbox-control` の1つだけ。
    Workerが一覧にない／個別scopeを選べないなら **ここで停止**。全WorkersやAdminへ置き換えない。新規Workerには別途本人によるbootstrapが必要であり、普通のCIへAdminを渡さない。
11. 同じaccountだけ・作成日+7日の期限を確認し、`Continue to summary` → `Create Token`。
12. この値も次のGitHub Secret欄へ直接コピーする。

account-owned Token作成には本人のAPI Token Provisioning能力またはSuper Administrator権限が必要。権限不足の場合、CI Tokenを広げず停止。

## GitHub: 2 Secrets + 2 Variables

対象sandboxを開く → `Settings` → `Secrets and variables` → `Actions`。

Secretsタブで `New repository secret`:

| Name | Secret入力欄に貼る内容 |
| --- | --- |
| `PLM_CF_D1_API_TOKEN` | D1 Tokenの値だけ |
| `PLM_CF_WORKER_API_TOKEN` | Worker Tokenの値だけ |

各入力後 `Add secret`。値はチャット/commit/workflow inputs/logへ記録しない。

Variablesタブで `New repository variable`:

| Name | Value |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | `6c8ccd6aface937ab5dabef61cb64534` |
| `PLM_D1_DATABASE_ID` | `18050cf6-934e-4f3a-a1cd-5041bac1c35e` |

各入力後 `Add variable`。既存値が正しければ再登録不要。Secret名の存在確認は可能でも、値の再表示はしない。

## 登録後の最初のworkflow

GitHub sandbox → `Actions` → `PLM Cloudflare Sandbox Setup Only` → `Run workflow`。
Branch: `main`、operation: `inspect` → `Run workflow`。

**`PLM Serverless Test Only`は選ばない。** そのworkflowの手動起動は将来の実callback試験用。

現在WorkのGitHub connectorは新規workflow_dispatchに対応していない。Workに別の安全な起動経路が確認できない場合、このRun workflowも本人操作が必要。Actions Secret登録だけで自動起動するとは約束しない。GitHub UIからWorkが起動可能かは、その時点で確認する。起動後の結果はWorkが監査する。

## 認証後の実行順序と停止条件

| 順序 | 実施内容 | 現在の実装/操作 |
| --- | --- | --- |
| 1 | auth確認 | `inspect`: account-owned Token active確認 |
| 2 | 既存D1取得 | 確定UUIDへGET。新規作成なし |
| 3 | ID + name照合 | UUIDとname両方一致しなければ停止 |
| 4 | schema inspect | sqlite_master、列、件数。既存job/不整合なら停止 |
| 5 | 必要時だけmigration | schema missingの場合だけ`migrate`。固定CREATE IF NOT EXISTSのみ |
| 6 | schema再確認 | `migrate`内で再確認、必要なら`inspect`。未知の書込み結果は読取照合、盲目的再送なし |
| 7 | Worker存在確認 | `prepare-deploy`: exact Worker settingsをGET。未存在なら停止/別途bootstrap |
| 8 | deploy/binding | 同workflowのWrangler deploy。DB固定、4 flags true |
| 9 | remote安全フラグ確認 | read-onlyの実active binding/flags証拠が必要。現workflowはこのremote read-backをまだ自動検証していない。deploy receiptだけではPASSにしない |
| 10 | 実往復直前で停止 | dispatch/callback credential追加、STOP解除、実job送信をしない |

現workflowはinspect/migrate/prepare-deployの段階選択式。全10段階の自動一本化は未実装。各段階をWorkが結果確認しながら進める設計で、利用可能なdispatch経路がなければ追加の手動Run workflowが必要。認証情報だけで自動完了すると扱わない。

## 最小の本人作業数

Workerが既に存在し、Variables/Secretsが未登録の場合:

- Token発行2件（同じCloudflareログイン作業内で実施）
- GitHub Secret登録2件
- GitHub Variable登録2件
- Workがworkflow起動できなければ最初のinspect起動1件

計6件の設定操作 + 必要なら起動1件。クリック総数ではない。Variablesが正しく登録済みなら2件減る。Worker未存在・ログイン/MFA・追加のworkflow起動・remote flag verificationには条件に応じた別操作が必要なので、全工程を6件だけで完了できるとは保証しない。

No Global API Key、no payments/upgrades、no production/PR15/PR16/n8n changes、no SNS通信/投稿、no live job。

## 公式資料

- https://developers.cloudflare.com/fundamentals/api/get-started/account-owned-tokens/
- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://developers.cloudflare.com/workers/authorization/workers/
