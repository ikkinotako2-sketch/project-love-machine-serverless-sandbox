# 1-account staged live migration runbook — NOT AUTHORIZATION

この資料は将来の手順であり、今回実行しない。現在Cloudflare凍結、live job/実callback=0。TEST_ONLY/DRY_RUN/NO_PUBLISH/EMERGENCY_STOP=true、render/API/Secret登録禁止。production/V1/n8n/PR15/16は触らない。

## 全段階共通

- 進行は前段階の証拠がPASSした場合のみ。未確認を成功扱いしない。
- 最初はsandbox専用account/resource。DB ID+名前、Worker `plm-serverless-sandbox-control`、repository `ikkinotako2-sketch/project-love-machine-serverless-sandbox` の三者照合。productionへfallbackしない。
- ログ/commit/chatへtoken/raw provider body/upload URLを出さない。認証値は保護された入力欄へ本人が直接登録。Account ID/DB ID等の識別子とSecretを分離する。
- 課金/Upgrade/購入/カード登録の要求はSTOP。account全体D1 Writeが本番D1へ届く構成はSTOP、先にsandbox account隔離。
- unknownは再initialize/dispatch/upload禁止。停止して既存reservation/resultを保持。失敗/timeoutをDoneにしない。
- rollbackは新しい入力停止・sandbox worker停止・一時試験権限の失効を基本とする。D1削除/unregister/reset/既存record削除/動画削除/production commit revertを自動実行しない。
- 各PASSにaccount/resource ID、対象commit、Actions run、remote schema/flags、安全にsanitizeされたresultを記録。署名/key/raw応答を証拠へ入れない。

## STOP地点と順序

| 段階 | 将来行う内容 | PASS条件 | STOP条件 | rollback/安全な停止 |
|---:|---|---|---|---|
| 0 | 本人の凍結解除承認と初回read-only認証 | sandbox scope、Free/$0、保護入力へcredential登録 | scope不明/本番D1共有/有料要求 | 未使用権限失効、凍結維持 |
| 1 | Cloudflare inspect | auth/account/Free entitlementの読取証拠 | 別account/401/403/応答不明 | 自動再送せずinspect保留 |
| 2 | D1 inventory | 既存plm-serverless-sandbox-stateのID+名前一致、同名1件 | 不存在/重複/ID不一致/未取得 | 再作成せず停止 |
| 3 | remote schema読取 | sqlite_master/列/件数/既存migration状態が読める | unexpected table/列/所有者データ/unknown | 書込せず停止 |
| 4 | 必要な場合だけsandbox migration | reviewed非破壊migration、同名/IDガード、再実行安全、既存件数不変 | destructive DDL/既存data差替え/本番D1権限/状態不明 | 新dispatch停止、schema保全。一時Write失効 |
| 5 | schema再検証＋backend実地障害試験 | remote uniqueness/CAS/claim/checkpoint/replay/audit・restart/競合証拠 | reference成功だけ/旧ownerが書込可/backup未確認 | 投稿を接続せずreadonlyへ戻す |
| 6 | sandbox Worker inventory→deploy | 既存Worker照合、DB binding ID一致、対象commit一致 | Worker不存在で通常Editorのscopeが不十分/Admin恒久Secret要求 | bootstrap別本人承認、一時権限だけ。未知deployは再送せずinspect |
| 7 | remote flags/binding確認 | 4flags=true、固定sandbox、SNS経路なし、DB=既存D1 | true以外/別binding/本番経路 | sandbox入力停止、Emergency Stop維持 |
| 8 | AI quota＋artifact容量確認 | 実project Free/model可用性、RPM/RPD/TPM、共有storage/既発生accrual/非課金設定、1-account envelopeに余裕 | 掲載modelだけ/0quota/容量超過/課金要求 | live generator/render未接続 |
| 9 | 必要なtest専用Secretだけ登録 | 保護欄、最小scope、rotation/失効経路、ログ露出なし | Secret値をchat要求/SNS本番credential/過大権限 | sandbox test権限失効、flags維持 |
| 10 | TEST_ONLY往復1件（別明示承認） | unique trial id、exactly1 reservation、1Actions run、signed callback、D1 terminal/CAS、usage測定 | Emergency Stop trueによる拒否/unknown/重複/2件目/署名異常 | 再送なし、再度停止、claim/tombstone保持 |
| 11 | 実AI1回（別明示承認） | quota確認済み、固定job、raw未保存、script semantic検証＋immutable checkpoint | malformed/partial/safety block/timeout/response不明 | checkpointあれば再生成なし、不明はreconciliation |
| 12 | 実render1回（別明示承認） | 同じjob/checkpoint、media quality gate、実size/duration/音声字幕/rights確認、artifact余裕 | generator変更/quality fail/容量/実size不明 | 自動rerenderしない、成功media/hash保持 |
| 13 | private YouTube1本（別明示承認） | 1-account OAuth、audience/synthetic/権利確認、durable reservation、uploaded video_idとprivate照合 | 公開設定/宣言未確認/既存claimだけ/unknown/二重run | 自動再投稿/動画削除なし、private維持、status照合 |
| 14 | 実1h | 実70分Environment遅延設定確認、video/job一致、collector evidence、collected | successだけ/slot欠測/unknown/deadline超過 | deadline警告、missingを0にしない、自動投稿なし |
| 15 | 実24h | independent slot、実due後取得evidence、nullable metrics保持 | virtual証拠だけ/他job/後着扱い不明 | inspect/reconcile、collected上書きなし |
| 16 | 実Improvement | validated7items、hypothesis only、sample status、次intent候補1件、監視反映 | 効果証明と誤認/duplicate候補/claim自動化 | planned-only、次投稿へ進まない |

段階5のremote atomicityとcallback transaction実装はまだ存在しない。現test_jobs migrationを適用しただけでpublish ledger backend完成にはならない。schema/store選定・remote adapter/workerの接続は、認証後にsandboxだけで実装・review・testする必要がある。SQLite/D1の採用決定を本runbookに含めない。

## Emergency StopとTEST_ONLYの正確な扱い

既存 `serverless/worker.mjs` はEMERGENCY_STOP=false以外を拒否する。現在trueを維持する条件下では段階10は**BLOCKED**であり、TEST_ONLYだから自動的に許可されるわけではない。

将来、本人が1件試験を明示承認した後も、この条件を勝手に緩めない。Emergency Stop解放の別承認か、SNSを永久拒否したままtest-only往復だけ許す新しい隔離経路の別レビューが必要。今回どちらも実装/実行しない。trial quotaは1件のみで、unknown→再送や別ID再試験を許可しない。

実AI/render/private投稿の段階は現在のoffline sandboxに投稿機能を入れる承認ではない。将来承認された隔離1-account実行領域でpinned既存Pipelineを再利用する方法を再レビューする。production main/PR15/16/n8nを変更する権限はこのrunbookから生じない。安全flagsの変更やproduction workflow dispatchにも別の明示承認が必要。

## credentialが戻る前に完了できないもの

実account inventory/plan/current allowance、active AI quota、OAuth/TLS/HMAC key、remote D1 atomicity/backup、runner停止証明、upload副作用照合、動画品質、実70分/24h待機。

次の最小本人操作は、sandbox専用Cloudflare accountの最初のread-only credentialを本人が保護された欄に登録すること。今はDashboard操作を要求せず、この地点で停止する。


2026-10-03更新: [最新read-only証拠と本人確認済みFree gate](PRE_MIGRATION_READ_ONLY_2026_10_03_JA.md)。Free/$0は本人Dashboard確認でPASS。最新inventory/schema/bookmarkは実read-only取得済み。migrationは引き続き未承認・実行禁止、isolationはunverified。

2026-10-03 05:31 JST: [Write account-owned activeと最終migration承認gate](MIGRATION_FINAL_GATE_2026_10_03_JA.md)。narrow D1 isolationのみ確認済み、Account Variable unverified、実migration0、allow false。
