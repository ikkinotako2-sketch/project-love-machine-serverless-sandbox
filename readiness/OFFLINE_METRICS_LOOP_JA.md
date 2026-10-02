# Terminal → virtual metrics → hypothesis → next intent (offline only)

2026-10-02。今回offline工程PASS、全自動化全体PARTIAL。
計画上の進行度85%→87%（+2pt）。残り実作業8–15時間の概算で、実測完了率ではない。認証/本人承認待ちは未定。将来の1h実検証は70分、24h実検証は約24時間+schedule遅延を別計上する。100+ accounts対応は別BLOCKER。

## 範囲と保護

sandbox `plm-offline-readiness-v1-20261002` だけ。読取り時production main SHA `fd4cd8b1f714d1c5ccffbabe88b89b64e36b468b`。production/V1/n8n/既存YouTube Pipeline/実Metrics/Improvementを変更しない。
PR15 head `a3bad01929b0db39499b4320182068f7a7e0047d`、PR16 head `e5ad13c1a92bf390272ce2c547f6b5ecaf8caa9c` はDraft・未merge。Cloudflare凍結、migration/deploy/live job/実callbackは未実施。
4安全フラグtrue。既存native seccomp/import/media-write guard内でテストする。render/FFmpeg/Docker/VOICEVOX/AI/YouTube/SNS/external socketは拒否。今回render_executions=0、runtime external_api_calls=0。以前のdummy render誤実行累積2件は監査資料に保持する。

## ループモデル

起点は明示的 `succeeded` terminal Record。今回のloopテストは前工程と同じ内容の凍結terminal fixtureを使用し、起点fixtureを作るためのclaim/dispatchすらこの新loopから呼ばない。failed/unknownやresult/evidence/fingerprint欠損では開始できない。これはreal callbackの認証ではない。

origin identity `(platform,account_id,job_id)` と result/intent/callback/fingerprint/completed_at を固定する。同じterminal再処理は同じloopへ戻る。異なるidentity/completed_atへの変更は拒否する。

| 段階 | 状態と条件 |
|---|---|
| succeeded入力 | metrics_pendingを作成。1h/24hはpending、metrics=null |
| 仮想時刻+1h | 1h due。fixtureがなければpendingのまま |
| 1h evidenceあり | 1h collected。24hは独立pending |
| 仮想時刻+24h | 24h due。明示evidenceでのみcollected |
| 7項目検証 | 24h collected必須、1h任意。improvement_ready |
| 次候補 | next_intent_planned。job_id=null、status=planned_only |

dueは既存 `SLOTS` と同じ1h=3600秒/24h=86400秒。deadlineは既存 `MAX_LATE` と同じ完了から3h/36h。ただし既存collectorの自動missed判定をここでは実装しない。deadline超過だけならmonitor警告 `deadline_exceeded` とし、observation_status=pendingを保持する。

collectedはidentity/evidence_id/slot/revision/observed_atが明示された固定fixtureのみ。1h/24hそれぞれのdue前に観測したcollectedは拒否する。dueを過ぎた24hが先着し、1hが後着する順序は許容する。

## Fixture・欠測・異常系

metricsの許容fieldは既存snapshot名と同じviews/likes/comments/averageViewDuration/averageViewPercentage/subscribersGained/subscribersLost/analytics_available。値は数値/bool/nullの固定fixtureだけ。raw API response/credential/余分なfieldを保存しない。

未取得値はnull。明示的な0だけ0とする。analytics_available欠損もnullで、Falseを捏造しない。集計snapshotは収集時の観測であり、正確な歴史intervalの復元ではない。

同じevidenceの完全replayはno-op。別内容で同じevidence、stale revision/観測時刻、同じslotの二重collection、collected上書きを拒否する。unknownはstickyで、deadline後もunknown、automatic resend/collected上書きは禁止。missedも明示evidenceとdeadline後の観測が必要で、自動上書きしない。

既存のpure monitor `observe_slot` を使う。due/deadline表示とobservation_statusを分けて保存する。実sleep/clock/cron/queue/APIはない。virtual clockの逆行は拒否する。

## Improvementは仮説

既存 `parity.validate_improvement` を再利用し、production `validate_ai` の7項目完全一致、各1–180 Python文字、analysis<=250を維持する。独立したpinned production関数oracleとも比較した。AIを呼んだことにはしないためmethod=offline_fixtureとする。

- hypothesis_only=true、effect_proven=falseを固定。
- sample_sufficientは既存rulesと同じ24h views>=30の条件。
- sample不足またはviews=nullはinsufficient_sampleとして保持。
- views>=30でも効果実証や統計的有意を意味しない。
- 1h未取得/unknownはviews_1h=null。元のevidenceを凍結し、後着1hで過去の改善根拠を捏造しない。
- 改善再実行の同一outputはno-op。違うoutputで保存済み仮説を上書きしない。

## 次PublishIntent候補

source terminal identityからdeterministic intent_idを作る。固定theme fixtureを使い、改善仮説のfingerprint/basis_job_idへリンクする。themeをAI生成しない。

候補はPublishIntent互換のidentity/themeにplanned-only metadataを付けたもので、実PublishIntent登録ではない。job_id=null。claim_permitted/dispatch_permitted/posting_permitted=false。

同じterminal/improvementを繰り返しても候補は1件だけ。8 threadsでのplan競合でも同じ候補、journalへのplan追加1回。候補のtheme差替えは拒否する。posting ledgerへ書込み、job mint、claim、dispatch、render、投稿の経路は実装していない。

## Snapshot / recovery

originとaccepted operation journal（tick/metrics/improve/planだけ）をJSON snapshotへ保存。restart相当の復元はjournal replayで行う。duplicate origin、不正operation、余分なfield、非canonical replayを拒否する。計算済みstateの勝手な注入を許可しない。

後着metricsより前に作った仮説の根拠もjournal順序で復元する。同一terminal再処理・改善再実行・restartで候補を重複生成しない。

RLockのatomicityは同じin-memory instanceだけ。実DB/複数process間のdurability、snapshotの認証/改ざん防止を保証するものではない。SQLite/D1をproduction backendに決定しない。

## テスト結果

新規loop60件。Python162→222 PASS、Node41 PASS、計263 PASS/FAIL0。

PASS: succeeded→metrics_pending→1h collected/pending→24h collected/pending→improvement_ready→next_intent_planned。

PASS異常系: failed起点拒否、identity不一致、stale/duplicate fixture、二重slot収集、24h先着、collected上書き、malformed metrics、7項目欠損、duplicate next intent、snapshot/restart。

PASS追加ケース: 1hだけ、24h未取得、24h後着、deadline後collected、explicit missed、unknown保持、欠測null、sample不足、concurrent plan。

**この仮想時計テストは、実際の70分Environment delayやlive 24h収集成功の証拠ではない。** 過去の実Metrics成功経路も変更していない。

## 残るUNVERIFIEDと次工程

real durable backend/複数runnerのatomicity・fencing、real callback認証、実AI/model/Free quota、render品質、1-account artifact容量/保持、実70分/24h collectorとの新経路接続。100+ accountsのstorage/Actions利用適合/quota/Secretsは別BLOCKER。

次は1-account用generation request contractと実地移行ゲート（durability、callback認証、artifact容量、無料枠）の静的整備。実接続・実AI・render・private投稿へ進む前の明示承認を維持する。現在ユーザー操作は不要。
