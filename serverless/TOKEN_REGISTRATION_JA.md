# Cloudflare Token登録 — 最新の安全条件

2026-10-02更新。前版の「同accountのD1 Writeを7日登録」は廃止。
**本番D1が存在、または有無未確認ならWrite Tokenの発行/登録/使用禁止。**

最新の比較・bootstrap手順: [ISOLATION_AND_BOOTSTRAP_JA.md](ISOLATION_AND_BOOTSTRAP_JA.md)。現時点ではTokenを発行しない。

## 確認済み非Secret識別子

- Account ID `6c8ccd6aface937ab5dabef61cb64534`
- D1 `plm-serverless-sandbox-state`
- DB ID `18050cf6-934e-4f3a-a1cd-5041bac1c35e`
- Worker `plm-serverless-sandbox-control`（存在未確認）
- GitHub `ikkinotako2-sketch/project-love-machine-serverless-sandbox`

## 本人のinventory確認とbootstrap完了後のみ登録

対象account → `Manage account` → `Account API tokens` → `Create Token`。

| Token名 | 選択権限 | Resource scope | GitHub Actions Secret名 |
| --- | --- | --- | --- |
| plm-sandbox-d1-inspect | D1 Read | 確認済みsandbox accountのみ | PLM_CF_D1_READ_TOKEN |
| plm-sandbox-d1-migrate-once | D1 Write | 同accountのみ、単一DB限定ではない | PLM_CF_D1_API_TOKEN |
| plm-sandbox-worker-deploy | Workers Editor | 同accountの個別existing plm-serverless-sandbox-controlのみ | PLM_CF_WORKER_API_TOKEN |

Read/Editorはtrial用7日。Writeは作業直前発行し≤1時間を目標にTTL設定、migration完了または中断直後にCloudflareで失効。その後GitHub Secretも削除する。TTLだけで権限隔離/一回使用を保証しない。Admin/Global API Key/全Accounts/全Workers/Zone/Routes/Billing/Token managementを追加しない。

権限・scope・期限を設定 → `Continue to summary`で照合 → `Create Token`。
値はsandbox `Settings → Secrets and variables → Actions → Secrets → New repository secret`へ直接コピーし、`Add secret`。チャット/画像/commit/logに値を送らない。

同ページのVariablesへ以下を`New repository variable`→`Add variable`で登録する:

| Variable | Value |
| --- | --- |
| CLOUDFLARE_ACCOUNT_ID | 6c8ccd6aface937ab5dabef61cb64534 |
| PLM_D1_DATABASE_ID | 18050cf6-934e-4f3a-a1cd-5041bac1c35e |
| PLM_CF_ACCOUNT_ISOLATION | 初期unverified。本番ありproduction_present。全inventory用途確認済みの場合だけsandbox_only_verified |

Variableをverifiedへ変更すること自体は権限隔離の証明にならない。本人確認記録が必要。現行画面の細かなラベルは実画面未検証、選択肢が合わない場合は停止する。

## 登録後の順序

sandbox `Actions → PLM Cloudflare Sandbox Setup Only → Run workflow`。
Branch main、operation inspect。

1. Read Token auth確認
2. 既存D1取得
3. DB ID+名前照合
4. schema/columns/COUNT inspect
5. isolation確認済みでschema missingの時だけmigrate（Write Token）
6. schema再確認、Write即失効・Secret削除
7. prepare-deployでexact Worker存在確認（Read + Editor Token）
8. 停止状態deploy/binding
9. read-onlyで実active binding/flags確認（現workflowでの自動read-backは未実装）
10. live試験直前で停止

WorkのGitHub connectorに新規dispatch機能がないため、安全な別起動経路が利用できなければ各Run workflowは本人操作が必要。全10工程自動一本化は未実装。

Worker未存在ならToken Editorはまだ作れない。本人Dashboardで停止placeholderを1回作成する推奨経路はAdmin Token不要。短寿命Adminの代替経路はprotected注入経路未確認のため実装/実行しない。

最初の本人操作はToken作成ではなく対象accountのD1一覧を開くこと。全inventory確認が終わるまでToken/migration/deploy/jobは停止。
