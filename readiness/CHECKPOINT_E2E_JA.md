# Script checkpoint + ledger + recovery offline E2E

2026-10-02。今回のoffline工程PASS、1-account全自動化全体PARTIAL。
計画上の進行度82%→85%（+3pt）。実測完了率ではない。残り実作業10–17時間の概算。認証/本人承認の待ち時間は未定、将来の1h結果待ちは70分、24h結果待ちは約24時間+実際のschedule遅延として別計上。100+ account対応は別BLOCKER。

## 変更範囲と維持条件

sandbox `plm-offline-readiness-v1-20261002` のみ。production main読取り時SHA `fd4cd8b1f714d1c5ccffbabe88b89b64e36b468b`。production/V1/既存YouTube Pipeline/1h/24h/Improvement/n8nは変更しない。
PR15 `a3bad01929b0db39499b4320182068f7a7e0047d`、PR16 `e5ad13c1a92bf390272ce2c547f6b5ecaf8caa9c` はDraft・未merge。Cloudflareは凍結し、migration/deploy/live job/実callbackを実施しない。

4安全フラグはtrue。既存native seccomp/import/media-write guardを必須にして全テストを実行。FFmpeg/Docker/VOICEVOX/render/AI/YouTube/SNS/external socketは拒否。今回render 0、runtime external API 0。前回dummy render誤実行の累積2件は `LEDGER_RECOVERY_JA.md` と `PARITY_1_ACCOUNT_JA.md` に維持する。

## E2Eの10工程

| 工程 | 保存・判定 |
|---|---|
| 1 PublishIntent登録 | Manual/Scheduleは同じ `(platform,account_id,intent_id)`。sourceで分岐しない |
| 2 初回job mint | fixture factoryは新規intentだけで呼ぶ。retry/restartでjobを作り直さない |
| 3 generation開始保存 | pending v1→claimed v2→generating v3。AIは呼ばない |
| 4 script checkpoint | parser-shaped `output` を検証し、script JSONをCAS保存。generating v4 |
| 5 script fingerprint固定 | sorted canonical scriptのSHA256。保存済みscriptはimmutable |
| 6 renderer/Pipeline入力変換 | 保存済みscriptからV2整形と既存18入力へマッピング。render/dispatchしない |
| 7 ready保存 | 完全な入力検証後にpayload/hash/readyを保存。v5 |
| 8 mock dispatch予約 | initializing v6を先に保存。外部送信はない。予約は最大1回 |
| 9 crash/restart | snapshot/reloadでcheckpoint/owner/version/job/hash/予約を復元 |
| 10 mock callback | fixture署名とidentity/versionを検証し、succeeded/failed v7へ。unknown経由ならversionは追加で進む |

script checkpoint直後はgeneratingのまま。checkpoint保存後crashなら、台本を再生成せずそのscriptからreadyへ進める。保存前crashならgeneration照合待ちで、自動再生成・再送を許可しない。

JSONキー順の問題を修正した。保存するscript JSONは元のfield順序を保持し、fingerprint用canonical JSONだけをsortする。これによりn8nのJSON.stringify由来の `scenes_json` 等がfixture上で文字列まで一致する。同じ内容のkey順だけが変わるreplayはno-opで、最初の保存順を維持する。

script fingerprintとrenderer payload fingerprintは別目的の値。ready payloadのscript部分がcheckpointと異なる場合は拒否する。snapshot復元でも両者の一致を検証する。

## Responseとsnapshotの契約

受け付けるgeneration fixtureは `{"output":{title,hook,narration,scenes,bgm}}` のdictまたはJSON文字列。raw AI HTTP response、余分なwrapper field、欠損、malformed JSON、duplicate keys、NaN/Infinity、必須field欠損、不正型、secret-shaped textを拒否する。失敗したresponseは保存せず、状態/owner/versionは変わらない。自動retryもしない。

ledger snapshotはformat2に拡張し、script_checkpoint_json/script_fingerprintを追加。旧format1はcheckpointなしとしてread可能で、checkpointを推測・捏造しない。既存Python108件とNode41件のbaseline testsは維持した。DB migrationではない。

E2E snapshotは `offline_checkpoint_e2e_v1`。raw generation response、callback envelope/signature、fixture keyを保存しない。JSON復元は上限1MiBのreference範囲。これは実disk/DBへのdurable保存ではない。

## Mock署名境界

`mock_signed_callback` はPUBLIC fixture keyだけを使うHMAC-SHA256。**公開keyなので認証ではない。** 実Secretを入力する引数、環境変数/credential読取、Cloudflare/API clientはない。productionへ流用しない。

- mode=`OFFLINE_MOCK_ONLY` を必須にする。
- exact allowlist fields、canonical body、署名、issued_atのfixture clockを検証。
- 有効時間はmock nowから過去300秒/未来30秒。実clock同期を検証したものではない。
- job/intent/account/platform/owner/versionを照合してからterminal mutation。
- 正確に同じcallback replayはno-op。stale owner/version、不正署名、body改ざん、別job、unknown intent、期限切れは拒否する。
- initializing/unknownは自動再initializeしない。unknownからはmockの照合結果だけでterminalへ進む。
- failedはDoneにしない。succeeded再実行はterminal no-op。

実署名、key保護/rotation、delivery/replay ledger、real callback authenticationはUNVERIFIED。

## 検証結果

Python162（既存108+新規54）PASS、FAIL0。
Node41（既存）PASS、FAIL0。
合計203 PASS、FAIL0。全て既存guard下で実行。

PASSした異常系: generation response欠損、malformed JSON、required field欠損、checkpoint前後crash、同じjobで別script、duplicate/stale callback、initializing/unknownからの再送試行、succeeded再実行。

追加PASS: 8 threads checkpoint CASの勝者1、key順replay、checkpoint/hash破損、checkpointとpayload不一致、旧snapshot読取、mock署名の改ざん/期限/identity境界。n8n抽出コードの独立oracleとfixtureの18入力を照合した。

## 残るUNVERIFIED

real durable backend、複数process/runnerのatomicity・fsync、owner handoff/fencing、外部APIとstate保存間のambiguous boundary、実AI response/model/Free quota、実render品質、artifact容量/保持、live metrics接続。

SQLite/D1をproduction backendに確定していない。snapshot/reloadはrestart相当のfixtureであり、実process crash時のdisk保存成功を証明したものではない。HMAC mockは実認証の代替ではない。

次の安全工程: terminal結果→1h/24h virtual-time monitor→Improvement7項目→次PublishIntentをつなぐoffline loop。実AI/render/private投稿/Cloudflare接続の前で停止を維持する。現在ユーザー操作は不要。
