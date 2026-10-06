# YouTube live接続前のread-only固定準備

既存productionは約98%。成功run `36153932146` の主要実装と現在mainは同一で、比較差分は `docs/COMMAND_CENTER.md` のみ。新serverless hardened live E2Eは別指標の0/1。

固定plan: `readiness/youtube-live-connection-plan.json`。準備parentは `28df45cdfcd34b5f57f9e34a334704b593a8264d`。これはdeploy承認やupload承認ではない。

## 現在確認と保存済み証拠の区別

10月4日のD1 schema証拠run `37170582256` は既存29 objectの比較基準。v2候補16 object、Queue/result候補13 objectとは別。保存済み証拠をcurrent PASSへ読み替えない。

新read-only workflowは新規push一回だけ。exact before、commit message、branch、attempt=1をworkflowとコードで検査する。最大3 request: token active確認、固定database metadata GET、sqlite_masterだけの固定SELECT。D1 queryのHTTP POSTは固定SELECT専用で、write SQL、行データ取得、Worker呼出、migration、dispatch、artifact/cache保存はない。redirect禁止、15秒timeout、256KiB response上限、retryなし。schemaはmemory内でsource catalogと照合し、stdoutは固定enum/count/booleanだけ。raw response、未知object名、SQL、exception文、tokenは保存しない。

source catalogは保存済みschemaと0008/0009をSQLiteで生成したsource由来objectのexact SHA256。未知object、既存object drift、部分適用では安全停止。schema確認が通っても、protected rows、Worker、OAuth、account-wide無料枠は未確認として維持する。

GitHub接続はsecrets metadata APIをサポートしていない。`PLM_YOUTUBE_GAME_001` は HISTORICALLY_CONFIRMED / CURRENTLY_UNVERIFIED。未確認を「存在しない」と扱わない。secret値の取得はしない。

## 依存順と停止境界

1. primary remote schema・bookmark・保護対象行の一致、現在のFree plan/全account使用量をread-only確認する。
2. 0008が未適用なら独立承認で0008だけ適用し、fresh postcheckして停止する。0009は別のexact import runner・write上限・独立承認が必要。部分適用を再適用しない。
3. existing Workerはtest専用。YouTube用D1 adapter/ingress/dispatchのbundleは未完成で、既存Workerをdeploy対象として流用しない。source/bundle hash未確定のためdeploymentはlaunchable=false。
4. production callbackは未接続。fixture verifierの構造を再利用し、専用32-byte以上のrandom HMAC key・key IDを双方に配置する必要がある。fixture key、OAuth、test callback keyを流用しない。配置は別承認。
5. canonical signed bodyにjob/intent/account/owner/epoch/fence、dispatch、run/attempt、workflow/script/media digest、result/video ID、private/notify=false/processed/QG、時刻をすべて束縛する。認証・時刻・durable outbox照合はD1 mutation前。結果保存/outbox確定/Queue COMPLETEは単一transaction。同一replayだけidempotent、変更replayとUNKNOWNは停止。
6. dispatchは新規durable claim→reservation→SENTを保存してから1回のみ。204は受付で成功証拠ではない。timeout/non204はUNKNOWN、再開・fallback・次jobを禁止。immutable SHAのdispatch ref受理も別途確認。実production dispatchはrender/uploadを開始するため明示承認が必要。
7. D1のQueue tableはCloudflare Queuesサービスとは別。Cloud Queue consumer/producer/cronは無効。Queue redeliveryからの再dispatchを禁止し、durable COMPLETE前に成功扱いしない。具体的ack/安全停止adapterは実装・検証待ち。
8. first private upload直前にQG PASS、新規job/claim/duplicate無し、upload1本、OAuth current readiness、現在$0、privacy=private、notify=falseを提示して停止する。public/unlistedは禁止。
9. 上記first live resultがprocessed/COMPLETEになった後だけtrigger/24時間観測計画へ進む。現在NOT_READY。

## $0条件

2026-10-06確認の公式公開条件: D1 Freeはread 5百万/day、write 10万/day、storage合計5GB。Queues Freeは1万operations/day、retention24h。GitHub public repositoryのstandard runnerは無料。artifactとPackagesの共有storage、使用済みGB-hours、account plan/残量は別途確認が必要。既存render/adapter/claim/result retentionは1/7/30/30日。今回の新workflowはartifact/cache upload=0。

- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/queues/platform/pricing/
- https://docs.github.com/en/billing/concepts/product-billing/github-actions

公開上限やdatabase sizeだけでaccount-wide $0をPASSにしない。DDL/indexのphysical rows writtenはCREATE statement数と異なるため上限を捏造しない。課金・quota不明なら有料upgradeせず停止。

安全停止は全4 flags=true、cron/consumer/routes無効を維持。claim削除、UNKNOWN reset、durable row rollback、再uploadをしない。004Hは永久consumed、APT未知GlobalErrorは未解決。既存productionの成功証拠とは独立で、今回APT/runtime/markerは0。
