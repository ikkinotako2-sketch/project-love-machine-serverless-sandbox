# D1権限隔離とWorker bootstrap — 決定済み安全方針

2026-10-02。設計・offline実装のみ。Token発行、remote migration/deploy、job送信は未実施。

## A. 単一D1のToken権限制限

公式permissionsではD1 Read/WriteはAccount permissions。2026-09-15の公式granular authorization記事はD1個別resource scopeを「次に導入」としている。2026-10-02の公式資料再調査では、単一D1 UUIDへaccount-owned Tokenを限定する実装済み方法を確認できない。

安全判断: **現時点では単一DB限定不可として扱う**。特定UUIDをコードへ固定してもTokenのprovider権限は縮まらない。将来UIに新機能が現れた場合も、公式仕様と実際の拒否試験を確認するまでは利用可能と扱わない。

### 発行禁止条件

同一accountに保護対象の本番D1がある場合、`D1 Write` Tokenを発行/登録/使用しない。未確認も禁止。期限を短くしても、この禁止を解除しない。

本人が全D1一覧（ページング/フィルター含む）と各用途を確認した証拠だけでaccountを判定する。名前がsandboxだから本番なし、と推測しない。確認後に新たな本番D1を追加した場合、同じaccountを再び混在扱いとしsandbox書込Tokenを失効させる。

| 安全策 | provider権限隔離 | 効果と残存リスク | 採用判断 |
| --- | --- | --- | --- |
| sandbox専用account | account境界で本番と分離 | 強い隔離。元accountの本番へToken権限を与えない | 推奨原則。ただし既存D1再作成/移動は禁止なので今回は自動適用不可 |
| migration時だけ短寿命Write | 同account内DB隔離なし | 時間を短くするだけ。有効中は他D1へ権限が届く | sandbox-only確認後の補助策 |
| Read/Write Token分離 | Readにはprovider上のwrite不可 | inspect/deploy時にWriteを渡さない。Read自体もaccount内読取範囲が広い | 採用 |
| migration後にWrite即失効 | 失効後は能力を除去 | 失効確認まで能力が残る。期限到来だけを即失効とはしない | 採用。本人が失効し、GitHub Secretも削除 |
| 本人が対象D1 Consoleで固定SQL適用 | CIへaccount-wide Write credentialを渡さない | 本人の既存権限は残るが委任credentialを新設しない。対象照合が必要 | 別途明示承認で検討可。今回は実施しない |
| Worker DB binding経由の限定操作 | Worker Editorだけでは完全なD1権限隔離を証明できない | bindingを持つWorkerは対象データへ到達。Editorはcode/bindingsを更新可能 | code側guardにすぎず、混在accountの隔離代替にしない |

**既存D1と分離accountの競合:** 既存 `plm-serverless-sandbox-state` が本番D1と同じaccountにある場合はBLOCKED。新accountを作れば既存D1が自動的に移るとは扱わない。export/import、新DB、DB ID差替え、D1削除/移動は本タスクで行わない。本人による別の移行方針承認が必要。

## 推奨Token構成

| Token名 | 権限/scope | GitHub Secret | 使用時点/寿命 |
| --- | --- | --- | --- |
| `plm-sandbox-d1-inspect` | D1 Read / 確認済みsandbox accountだけ | `PLM_CF_D1_READ_TOKEN` | inspectとdeploy前schema確認。trial用7日、その後必要に応じ更新 |
| `plm-sandbox-d1-migrate-once` | D1 Write / 同accountだけ | `PLM_CF_D1_API_TOKEN` | 明示的migrateだけ。作業直前発行、≤1時間を目標にTTL設定、完了または中断直後に失効 |
| `plm-sandbox-worker-deploy` | Editor / 個別existing `plm-serverless-sandbox-control`だけ | `PLM_CF_WORKER_API_TOKEN` | 通常deploy。trial用7日 |

TTLの画面精度は未確認。1時間を設定できなければ自動で長期間へ広げず、本人の即時失効を前提に再確認する。

Write tokenへToken Provisioning/management権限を追加して自己失効させない。自動失効に別の広いTokenを導入しない。失効は本人がAccount API tokensで対象を失効/削除し、必要に応じownerの既存認証で公式token delete APIを使用する。GitHub Secret削除だけではCloudflare Tokenは失効しない。誤って広いTokenをRead Secretへ入れても名前だけでは権限が縮まらないため、登録前summaryの権限確認が必須。

非Secret Variables:

- CLOUDFLARE_ACCOUNT_ID: `6c8ccd6aface937ab5dabef61cb64534`
- PLM_D1_DATABASE_ID: `18050cf6-934e-4f3a-a1cd-5041bac1c35e`
- PLM_CF_ACCOUNT_ISOLATION: 初期/不明 `unverified`。本番存在時 `production_present`。本人の全inventory用途確認後に限り `sandbox_only_verified`。

最後のVariableは証拠の代わりではなく、本人確認済みの記録をworkflowへ渡すgate。コードはmigrate/prepare-deployが確認済みでない場合HTTP前に拒否する。inspectはRead Tokenのみ使用。通常setupにWrite secretを渡さない。

## B. Worker未作成時のbootstrap

### 推奨: 本人の既存Dashboard権限で停止用Workerを1回作成

1. D1/account用途確認完了後、対象accountのWorkers一覧でexact名を確認。同名があれば作成せず内容を確認する。
2. 存在しなければ `Workers & Pages` → `Create application` → Worker作成を選択し、名前を `plm-serverless-sandbox-control` に固定する。実画面の名称が異なる場合は対応するWorker作成操作を確認し、Pagesや有料productへ進まない。
3. `bootstrap-placeholder.mjs` のコードだけを設定。全requestへ503/disabledを返し、flagsはsourceでtrue固定。D1 binding、Secret、Cron、Queue、SNS/GitHub dispatch、custom domainは付けない。
4. 本人が最終作成/deployを承認する。これは実往復試験の承認ではない。Free/$0条件と正しいaccount/nameを最終確認。Upgrade/card要求があれば停止。
5. 作成を読み取り確認し、そのWorkerだけのEditor Tokenを発行/登録する。通常CIへAdminを渡さない。
6. 後日の停止状態deployでDB bindingと4つのtrue env varsを配置する。placeholderはenvが無い/falseでも常に停止する。

推奨経路では **Admin Tokenを1つも発行しない**。本人のDashboard権限で作成するため、通常CIへのAdmin Secret登録工程も不要。Work Browserで操作できない現状では作成操作は本人が行う必要がある。

### 代替: 短寿命bootstrap専用Admin Token

公式の新規Worker作成にはWorkers product-level Adminが必要。まだ存在しないWorkerへper-Worker scopeは設定できない。このTokenは対象accountの他Workersにも権限が及ぶ。

代替を使う条件は、完全sandbox account（本番D1/Worker/他本番resourceなし）と、本人が権限・用途・expiryを最終確認した別途明示承認、protectedな一時credential入力経路、create前のread-only exact名確認、fixed placeholderのみ、create後のread-only確認、Token即失効確認。

- Token名案: `plm-sandbox-worker-bootstrap-once`。
- Scope: 対象sandbox accountのWorkers product Adminだけ。D1/Routes/DNS/Billing/Token managementなし。
- TTL≤1時間を目標、常設GitHub Actions Secretへの登録禁止。
- 安全な一時実行環境でのみ使用。Workには現在protectedなToken注入経路が確認できず、GitHubへの臨時credential委任も未設計なので、この代替は **設計のみ/実装不可として停止**。
- create応答喪失時は再createしない。読取で存在・内容を照合し、unknownなら停止。
- 一時Adminを通常Editorへ自動変換するものではない。Admin失効と新規Editor Token発行は独立したowner操作。

OAuth Device Flowはgranular authorization非対応なので、bootstrapだけの限定権限にしたと偽らない。一時メンバーへproduct Adminを付ける方法も同じ権限幅を持つため、この問題の回避策として自動採用しない。

## 現在の判定と次の1操作

設計/offline gateは準備済み。実accountの本番D1有無とWorker存在は未確認。Token発行、migration、deploy、live jobはすべて停止。

本人がDashboardを開けるようになったら、**Account ID `6c8ccd6aface937ab5dabef61cb64534` の `Storage and databases → D1 SQL Database` 一覧を開く**。次は一覧と用途を確認し、Token作成へまだ進まない。この1操作を先に行う。

既存V1/V2/YouTube/production repo/PR15/PR16/n8nは無変更。TEST_ONLY/DRY_RUN/NO_PUBLISH/EMERGENCY_STOP true、unknown自動再送なし、D1再作成/破壊migrationなし、live上限1件、試験前明示承認を維持。

## 公式根拠（2026-10-02再確認）

- https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- https://blog.cloudflare.com/workers-granular-authorization/ （D1 resource scopeはWhat's next）
- https://developers.cloudflare.com/workers/authorization/workers/ （existing Editor/new product Admin、binding権限）
- https://developers.cloudflare.com/fundamentals/api/get-started/account-owned-tokens/
- https://developers.cloudflare.com/fundamentals/api/get-started/create-token/ （TTL）
- https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/delete/
- https://developers.cloudflare.com/workers/get-started/dashboard/
