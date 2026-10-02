# 1-account offline final readiness — 2026-10-02

今回offline統合はPASS。全体PARTIAL、live gate BLOCKED。
進行度87→92%（+5pt）は計画上の概算であり、live成功率ではない。残り実作業6–12時間（backend実装/実地障害検証が長引く場合は見積り更新）。外部認証/承認待ちは未定。将来70分/24h metricsの待ち時間は別計上。100+ accountsは別BLOCKER。

## 保護と実物照合

対象はsandbox branch `plm-offline-readiness-v1-20261002` のみ。production main `fd4cd8b1f714d1c5ccffbabe88b89b64e36b468b` のPipeline/render/adapter/1h/Improvement/Command CenterをGitHub実物から再読。pinned parity sourceに対し入力18項目・7項目validatorの変更がないことを確認。export SHAは `final_sources.json`。credentials/HTTP headersを抽出・コピーしない。

PR15/16はDraft・未merge、head不変。production/n8n/V1/既存成功経路を変更しない。Cloudflare凍結、migration/deploy/実callback/live jobなし。Secret追加なし。4安全フラグtrue。現在のn8n live状態はUNVERIFIED。

今回runtime render_executions=0/external_api_calls=0。過去のdummy render誤実行2件は既存監査に残す。本資料の0は過去を取り消さない。GitHub読取/commitと公式資料の調査はテストruntimeのAPI件数ではない。

## 完成したoffline境界

| 境界 | 内容・制限 |
|---|---|
| Generation | one-account theme、7項目hypothesis、固定候補model、JSON Schema request proposal。client/URL dispatch/credential読取なし |
| Parser | UTF-8 byte上限64KiB、duplicate key/partial/異常型/非有限数/深度/制御文字/孤立surrogate/Unicode noncharacter/bidi制御を拒否。通常emoji可。外部文字をNFKCで勝手に変更しない |
| Provider response | one STOP candidateのtextのみ。metadataはdiscard、tool/thought/media/blocked responseは拒否。raw responseをledger/journalへ保存しない |
| Retry | 429/500/503はquota review後の候補だけ、最大2retry（3attempt）。timeout/ambiguousはreconciliation、checkpointがあれば再生成しない。自動retryは常にfalse |
| Checkpoint | same job/different script拒否、restart後checkpoint優先。JSON-valued Pipeline文字列はscene/bgmの固定field順で復元し、snapshotによるキーsortが入力byteを変えない |
| Durable contract | intent一意/mint once、claim/checkpoint CAS、単調version、immutable hash、initialize reservation、terminal/replay、slot CAS、hypothesis checkpoint、next候補一意、audit |
| Fencing | owner epoch+version。旧owner・古いepoch拒否。handoffは公開mockの停止/副作用settled/supervisor証拠が必須。時刻経過は引数にない。initializing/unknownは移管禁止 |
| Callback | plm-callback-v1 domain-separated HMAC、canonical JSON、issued_at(-300/+30秒)、delivery id、account/job/platform/intent/owner/epoch/version binding。current/previous fixture key overlap、改ざん/reorder/extra/replay拒否 |
| Transaction boundary | callback replay marker+terminal+audit+metrics起点をreference authority lockで一括確定。invalid callback/時刻のrollbackを検証 |
| Command model | stage/checkpoint/event/時刻/deadline/独立slot/failed/unknown/manual reconciliation/safe actionを一画面相当dictに統合。workflow successだけではhealthyにしない |
| Final gate | 実テストsuite成功・必須test IDs・件数一致・skipなしを要求。CIログへFINAL_READINESS_GATE。offline PASSでもlive_ready/posting_permitted=false |

新しいgeneration Unicode/制御文字制限は移行先の安全境界。n8nが受け入れる全入力と同値とは主張しない。新promptもn8n agentの完全同値ではない。7項目producer validator自体は変更せず、generation request境界で追加の文字安全制限を適用する。

## Backend-neutral invariants / ownership

`DurableStoreContract` はinterface、`ReferenceAuthority` と独立 `ReferenceClient` はsimulation。既存Ledger/Checkpoint/Loopを包み、既存モジュールの動作を変更しない。

本番backendは単一authorityで以下を一transaction/CAS相当で実現する必要がある。

1. UNIQUE(platform,account_id,intent_id)、UNIQUE(job_id)。初回insert+job mintを不可分にし、同じintentの内容変更を拒否。
2. WHERE owner/owner_epoch/version一致の更新、version+1。checkpoint/hash・initialize reservation・監査を同時保存。
3. delivery id一意とresult確定を同時保存。署名検証だけでnonceを先に消費しない。rotationでも同じdelivery idを別payloadへ再利用しない。
4. metrics slotとrevisionのCAS、collected上書き禁止。improvement/next意図の一意checkpoint、欠測はnull。
5. backup/restore/retention後もterminalとreplay tombstoneを維持。artifactやGit commit競合をatomic claimと扱わない。

RLockの成功は実DB/複数process/複数runner間のatomicity証明ではない。8 independent handles/threadsの競合と、processに相当するread/write interleaving、journal restartを検証した。実fork/runner/DB試験は未実施。SQLite/D1を採用決定しない。

handoffで受け取る証拠は公開fixtureで、実停止や本人承認の証明ではない。本番では信頼できるsupervisorが旧runnerの確実な停止とin-flight外部副作用を確認する必要がある。外部APIはfencing tokenを理解しないため、ローカルepochだけで既に飛んだ投稿を無効化できない。initialize request送信→受付→response前crashは引き続きmanual reconciliation。安全なlive handoffはUNVERIFIED。

journal snapshotは改ざん認証を提供しない。回復試験用であり外部から受信する認証済み入力ではない。replay retentionはjob/result寿命以上が必要、削除は今回実装しない。

## Callback本番前の残り

公開fixture keyは認証情報でも実認証でもない。実keyを渡すAPI/env lookupは実装しない。
本番はTLS、bounded body、constant-time signature、key_id allowlist、独立したaccount/job scope、atomic replay ledgerが必要。前keyのoverlapは最大replay/遅延delivery窓を踏まえ明示期限を持たせ、漏洩時は即停止・失効する。今回current/previousはmockのみ。expiry後に再署名して再投稿する経路を作らない。

## Artifact / media lifecycle

production実物では4artifact:

| artifact | 内容 | 現在retention | 用途 |
|---|---|---:|---|
| rendered-short-job | short.mp4/payload_snapshot.json/render-result.json | 1日 | render job→adapter jobへのmedia受渡し |
| youtube-result-run | youtube-result.json | 7日 | adapter→pipeline result、video_id等 |
| pipeline-result-job | pipeline-result.json | 30日 | n8n互換・監査。sanitized plm-resultsにも保存 |
| plm-youtube-claim-hash | run-id.txt | 30日 | 既存adapterのcross-run duplicate check |

**既存claimはartifact一覧のcheck→uploadであり、原子的DB claimではない。expiry後や複数run競合を完全に防止する証拠ではない。既存成功経路は変更しないが、新経路のlive二重投稿防止は、別途durable claim+副作用境界の接続検証が済むまでBLOCKED。**

投稿成功後、1h/24hに必要なのはvideo_id/account/job/completed_at/metadata・snapshotでありmp4不要。mediaはrecover/re-upload用途の許可とambiguous照合が済むまで自動削除しない。callback/metrics payloadへmedia/rawレスポンスを入れない。

候補（未適用）: result artifactsを1日にしdurable sanitized resultを維持、同一job内render→uploadならmediaartifactを省けるが既存workflowの構成変更になるので別レビュー必須。1day mediaも失敗復旧窓を超える可能性があり自動rerender/reuploadを許可しない。

50MiB動画+0.1MiB render metadata+各0.01MiB result+128byte claim、1投稿/dayの仮定では定常約50.47MiB、約35.49GiB-hours/30日（既存共有使用量を除外）。100MiB動画なら約100.47MiB。実圧縮artifact size/owner Free allowance/既存共有使用量/既発生accrual/課金防止設定はUNVERIFIED。Free500MBは公式plan表の参考値であり、このownerの空き容量を確認したものではない。public標準runnerの無料とartifact無制限を混同しない。安全な$0を確認するまではupload試験へ進まない。

## n8n V2責務の最終棚卸し（主判定）

| 責務 | 判定 | 残り |
|---|---|---|
| Schedule | DESIGN PASS | cron/timezone/occurrence identityのlive timer接続 |
| Manual Form | DESIGN PASS | 実フォームUI/認証/submit identityはNOT MIGRATED、共通intent模型のみ |
| Theme source | NOT MIGRATED | 固定fixtureのみ、継続theme供給/品質/収集は未接続 |
| Improvement feedback | OFFLINE PASS | 既存7項目+V2 consumerのfixture parity、live取得は未接続 |
| Script generation | DESIGN PASS | request/parser完成。実prompt/model/output品質はUNVERIFIED |
| Structured validation | OFFLINE PASS | schema-shaped V2整形と追加安全parser、全n8n型変換はUNVERIFIED |
| Queue | DESIGN PASS | reference一意intent。実永続queueは未接続 |
| Processing | OFFLINE PASS | claim/generating/readyとcheckpoint/restart |
| Claim | DESIGN PASS | CAS/epoch simulation、実atomicityはUNVERIFIED |
| Dispatch | LIVE CONNECTION REQUIRED | mock reservationのみ、実送信0 |
| Result wait | DESIGN PASS | callback/event/deadline模型、実timer未接続 |
| Timeout | OFFLINE PASS | deadlineとunknown分離、自動再送禁止 |
| Recovery | OFFLINE PASS | snapshot/checkpoint/unknown/manual照合模型 |
| Done/Failed | OFFLINE PASS | explicit terminalのみDone、失敗をDoneにしない |
| 1h | LIVE CONNECTION REQUIRED | virtual fixture PASS、実70分の証拠ではない |
| 24h | LIVE CONNECTION REQUIRED | independent slot PASS、実24hの証拠ではない |
| Improvement | OFFLINE PASS | 7項目/仮説/sample不足/次候補一意、実AI未実施 |
| Command Center | DESIGN PASS | readonly integrated model、既存画面/更新workflowは未変更 |

この棚卸しは責務単位。V2から切断・移行済みという意味ではない。manualが既存queue claimを迂回する差はexportどおり保持し、移行先共通入口を別設計にした。VOICEVOX/FFmpeg/LocalServiceConfig等の既存local分岐も削除しない。PC非依存のtargetは既存GitHub render経路。

## Readiness gate（18項目）

| 判定 | 項目 |
|---|---|
| OFFLINE PASS（8） | offline parity、generation contract、duplicate prevention、recovery、Pipeline contract、metrics loop、Improvement loop、next-intent uniqueness |
| DESIGN PASS（3） | durable store contract、fencing、callback auth boundary |
| UNVERIFIED（4） | artifact/storage、AI quota、実backend readiness、実render readiness |
| BLOCKED（3） | Cloudflare readiness、Secrets readiness、publish readiness |

全suite PASSでoffline_complete=true。live_ready=false/posting_permitted=false。callerのfixture trueでlive gateへ昇格できない。test失敗、必須test欠損、skip、件数不一致はoffline gateも拒否。

## 公式資料照合（複数source、確認日2026-10-02）

Google:
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/deprecations
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/structured-output （更新2026-09-23）
- https://ai.google.dev/gemini-api/docs/generate-content/structured-output （更新2026-09-02）
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/troubleshooting

一致: schema subsetでsemantic検証必要、RPM/TPM/RPDはproject単位、quotaはAI Studioのactive値確認が必要。pricing/model/deprecationの照合では3.8 Flash/3.5 Flash-Liteは候補、2.5系は過去利用者限定という注意。候補を実project利用可能と扱わない。
相違/更新: current guideはInteractions response_format、GenerateContent guideはLegacy表記。REST APIのresponseMimeType/responseSchema等はresponseFormat推奨を明記し、古いSDK例はresponse_json_schemaを残す。今回のdata-only proposalはGenerateContentのresponseFormat.text.mimeType/schemaを使い、既存n8nモデルやproductionSDKを変更しない。SDK/providerのlive受理はUNVERIFIED。

quota planは1script+1hypothesis/day、各最大3attempt=最大6requests/day、1request/minuteの設計上限、output cap4096。入力tokenは実tokenizer/count確認が必要。free modelが掲載されても6requests/dayを保証しない。実quota不足はretryを増やさずSTOP。tools/grounding/cache/batch/paid fallbackなし。

GitHub:
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://github.com/actions/upload-artifact
- https://docs.github.com/en/organizations/managing-organization-settings/configuring-the-retention-period-for-github-actions-artifacts-and-logs-in-your-organization
一致: public標準runner無料、artifact shared pool/retentionを別管理。公式Actionのretention最小1日。runner無料はstorage無料無制限ではない。$0は実owner usageが未確認なのでUNVERIFIED。

YouTube:
- https://developers.google.com/youtube/v3/docs/videos
- https://developers.google.com/youtube/v3/docs/videos/insert
一致: privacy/audience/synthetic declarationは別。fixtureのfalseを実動画の正しい宣言と扱わない。privateも投稿許可ではない。quota/rights/宣言/ユーザー承認は実投稿前STOP。

## 今回のテスト

Python354 PASS/FAIL0（既存222+新規132）、Node41 PASS/FAIL0、計395 PASS。新規115+CI gate6+追加境界6+source/monitor5。
全てmandatory kernel guard内で実行。外部socket/exec/import/media write拒否probeを含む。実DB/実process/APIの成功と混同しない。

## 次に必要なユーザー操作

認証が利用可能になった時点で、sandbox専用Cloudflare accountの最初のread-only credentialを本人が保護された登録欄へ設定する工程。値をchatへ貼らない。凍結解除と段階ごとの明示承認が必要。共有accountに保護対象D1があればD1 Writeを発行しない。今は操作を要求せず停止する。
