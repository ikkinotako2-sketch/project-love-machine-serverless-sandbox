# Generalized behavior test STOP / PARTIAL_APPLIED

2026-10-04、[approved run 37167246069](https://github.com/ikkinotako2-sketch/project-love-machine-serverless-sandbox/actions/runs/37167246069) attempt1。固定33-step testを1回開始し、step3でSTOP。step4〜33は未送信。SUCCESS条件は達成していない。再実行/再送/削除/reset/rollbackは行わない。

plan raw SHA256 `452fd980ba62164f71cfe3841ea7d399ef988c6e259945d5c67487a44eaf52c7` exact、不変。実送信前fresh gate PASS: Behavior Token active/finite expiry verify1、Read Token監査34、schema5tables/11triggers/14autoindexes exact、全5table row0、既存証拠不変、inventory exact、DBsize196608、fresh bookmark、migration成功receipt exact、prior behavior execution0。全167runs/9pages、current run unique、fixed code pinとbranch head一致。

| Step | 結果 | Logical changes |
|---|---|---:|
| 1 job_create | APPLIED、full read-back一致 | 1 |
| 2 unique_intent_duplicate_noop | NO_OP、full read-back一致 | 0 |
| 3 job_identity_conflict_rejected | UNEXPECTED、期待safe trigger token未確認、即STOP | 未確認 |

step3 diagnosticsはcode7500 / safe_message=`[REDACTED_UNRECOGNIZED_MESSAGE]`。raw response/messageは保存していないため、実provider文言を推測・復元しない。既知trigger tokenとexactに照合できず、承認済みunknown停止条件を適用した。

mutation sends3、確認できた成功logical changes1、matched steps2。reconciliation1セットのみ。read-only callsはfresh監査34＋実行read-back/post54、Behavior verify1、合計89 Cloudflare read-only calls。mutation HTTP3。application retry/resend/fallback/automatic rollback0。

Read-only reconciliation結果 **PARTIAL_APPLIED**。保存row:
- `plm_rt_v1_job`1行: `rt-behavior-20261004-001`、intent `private-roundtrip-behavior-20261004-001`、account `youtube_synthetic_rt_001`、owner_a / epoch1 / fencing1 / version1 / ACTIVE、result_id=null。
- script/render/effect/callback各0行。step3前と同じjob identity・intent・versionを確認。
- schema FULL_APPLIED、5tables/11triggers/14autoindexes exact、既存stage2 SUCCESS3row・atomicity row・test_jobs0・全既存schema/indexes・_cf_KV schema不変。
- _cf_KV content=NOT_APPLICABLE_RESERVED_UNQUERYABLE。
- fresh bookmark `0000001f-00000002-000050fa-e52f8331246183620a42e417254a4e4f`。post-check set1、追加D1 audit/reconciliationは実施しない。

prepare offline CI [37167181988](https://github.com/ikkinotako2-sketch/project-love-machine-serverless-sandbox/actions/runs/37167181988) SUCCESS: Python488＋Node687＝1175 tests全PASS。今回のremote responseはoffline fixtureの期待response形式と一致せず、remote testのSUCCESSとは区別する。

approved workflowをhard-disabled / allow=false / UNAPPROVEDへ戻し、元のplaceholder/preflightもdisabledをread-back確認する。SENT履歴と今回のdurable receiptにより今後の同runner再開を禁止する。live_ready=false / posting_permitted=false / 4安全フラグtrue。

Worker / AI / render execution / YouTube / SNS / external provider=0、DELETE / DROP / reset / rollback=0。production / sandbox main / n8n / V1 / 既存YouTube Pipeline / PR #15/#16変更なし。migration receipt・既存stage2証拠・今回のsynthetic jobを保持する。

次の本人操作:
1. Cloudflare `plm-sandbox-d1-roundtrip-behavior-once` Tokenを失効/削除。
2. GitHub Secret `PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN` を削除。

`PLM_CF_D1_READ_TOKEN` は維持する。ここで停止する。decoder変更による再送や残step再開は今回の承認に含まれない。
