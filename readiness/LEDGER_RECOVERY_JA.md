# Common PublishIntent ledger + recovery offline reference

2026-10-02。今回のoffline検証はPASS。1-account全自動化全体はPARTIAL。
進行度はユーザー基準78%から計画上82%へ（+4ポイント）。実測した完了率ではない。残り実作業12–20時間の概算（offline境界/fixture拡張、実backend接続・安全確認、段階テスト）。Cloudflare認証待ち、承認待ち、1h/24h metricsの自然経過待ちは含めない。100+ account対応も含めない。

## 保護条件と現状照合

- 対象はsandbox `plm-offline-readiness-v1-20261002` だけ。production/main、sandbox/main、PR15/16、n8nは変更しない。
- production main読取り時のSHAは `fd4cd8b1f714d1c5ccffbabe88b89b64e36b468b`。以前の `c869b41f941b9cdff45cd2ceb16532de777b6ac1` からの差分は `docs/COMMAND_CENTER.md` の更新のみ。既存validator/Pipeline契約は変わらない。これは本作業の変更ではない。
- PR15 `a3bad01929b0db39499b4320182068f7a7e0047d`、PR16 `e5ad13c1a92bf390272ce2c547f6b5ecaf8caa9c` はDraft・未merge。ClaimStore/SQLite本番採用は未決定。
- V1と既存YouTube Pipeline/1h/24h/Improvement成功経路を保護。n8n liveは操作しない。n8nのProcessing/claim確認、二重投稿防止、失敗をDoneにしない方針を維持する。
- Cloudflareは凍結。migration/deploy/callback/live jobを実施していない。認証問題は再調査しない。
- TEST_ONLY/DRY_RUN/NO_PUBLISH/EMERGENCY_STOP=true。実AI、render、Docker/FFmpeg/VOICEVOX、YouTube/SNS通信・投稿、Secret登録は禁止。

## 前回の監査事故と新ガード

前工程で `test_real_render_and_quality_gate` をproduction/PR15 snapshot各1回、計2回誤実行した。3.2秒dummy renderで、一時ファイルは終了時削除された。この事実を消さず、重要な監査事項として扱う。今回はこの事故を再発させないため、選別から実行拒否へ防御を追加した。

1. Trusted bootstrapだけでC guardをコンパイルし、純粋比較用Node oracleをnative guard付きで先行起動する。
2. Linux seccomp TSYNC + no_new_privsをPythonへ設置。全スレッド/子孫にexecve/execveat、socket/connect/send、io_uring等の拒否を継承する。NodeもLD_PRELOAD constructorで同じフィルタを設置する。
3. Nodeは `--test-isolation=none` でテストし、子プロセスを必要としない。Node24を使用する。
4. Python import hookとaudit hookでrenderer/FFmpeg/VOICEVOX/Docker/AI SDKのimport、プロセス起動、socket、media書込みを拒否。Nodeにも通常のfs media書込み拒否を加える。
5. native exec/socketの無害なprobeがEPERMにならなければ開始しない。flags不足、library不足、seccomp設置不可でも停止する。Pythonの各テストmoduleもguarded runner以外からの起動を拒否する。
6. checkoutはpersist-credentials=false、CI contents:read。Secretsを渡さない。oracleへ渡す環境はPATHと保護フラグ/native guardだけ。

これはレビュー済みofflineテスト内の誤起動防止であり、悪意のあるprivileged hostやCI定義改変への完全なsandbox保証ではない。Python/Nodeのmedia/import hook単体をsecurity boundaryとは扱わない。OSのexec/network拒否が主要な強制境界。ガードより前のsetup/コンパイル/Actions準備は信頼するbootstrapで、render実行コードを含まない。

証拠: Pythonのnative socket/exec拒否probe、禁止program/import/media write probe、Nodeのnative拒否probeがPASS。CIログの `OFFLINE_GUARD_EVIDENCE` と `NODE_OFFLINE_GUARD_EVIDENCE` を確認する。render_executions=0はこれらの実行拒否とテスト経路に基づく判定で、任意の外部環境を監視した数値ではない。今回のrender 0、前回累積dummy render 2は区別する。

## モデル

`PublishIntent(platform, account_id, intent_id, theme)` をManual/Scheduleとも同じ正規化へ渡す。sourceは起点属性であり、冪等キーに含めない。同一intentかどうかは、呼出側が同じpersisted intent_idを使うことで決まる。themeだけから意図を推測したり、submitごとにidentityを作り直したりしない。

ledger keyは `(platform, account_id, intent_id)`。registerは新しいkeyでだけpure fixture factoryを呼びjob_idをmintする。同一intentのretry/restartは保存済みjob_idを返す。theme変更や別intentで同じjob_idは拒否する。

claimはowner固定。同一ownerの再読込はidempotent、別ownerは拒否。mutationはlock + owner/version CASでversionを進める。timeout経過によるtakeoverはない。owner handoff/fencingは未実装。

contentは既存offline payload validatorを通し、canonical JSONとSHA256をready遷移時に同時保存する。fingerprint/payloadはimmutable。同一内容のbind replayはno-op、違う内容は拒否する。

| 現在状態 | offline操作／recovery |
|---|---|
| pending | 初回claimのみ |
| claimed | fixture generation再開候補。owner/version維持 |
| generating | 保存されたscriptの照合。自動再生成・外部AI許可ではない |
| ready | mock dispatch予約候補 |
| initializing | 照合のみ。予約後・実send前にcrashしても保守的に再送禁止 |
| unknown | 照合のみ。ready/initializingへ戻せない |
| succeeded | terminal/no-op。正しいownerの確定結果だけqueue_done |
| failed | terminal_failed。queue_done=false |

reserve_mock_dispatchはreadyからinitializingへの保存だけ。外部送信しない。各jobの予約は最大1回。fixture callbackのowner/versionが一致すればinitializing/unknownからsucceeded/failedへ移る。正確に同じcallbackの再送はno-op。別結果へのterminal上書き、stale owner/versionは拒否する。

**callbackはfixtureであり、実署名・認証を実装したものではない。** 旧ownerから新ownerへの安全な権限移管は別工程。実署名、fencing、durable atomic transactionはUNVERIFIED。

## 障害テスト

- claim直後crash→snapshot復元→同じowner/jobで再読込、dispatch予約0。
- script生成後・保存前crash→generating保持→saved-script reconciliation。
- content保存後crash→ready/fingerprint/payload/version保持。
- dispatch予約前crash→ready、予約0。予約保存後・send前crash→initializing、再送禁止。
- 外部応答不明→unknown、再initialize禁止。fixtureの照合結果のみterminalへ移せる。
- callback重複→no-op、stale owner/version→拒否。
- succeeded後restart/replay→no-op、failedをDoneにしない。
- 8 threadsのclaim競合→所有者1。register競合→mint1回。同一ownerのdispatch予約競合→予約1回。
- 全8状態のsnapshot/reload、fingerprint破損/重複identity/secret列/不正version/identifier/path traversalを拒否。

RLockのatomicityは同一in-memory instance内だけ。snapshot/reloadはprocess restart相当のfixtureであり、disk fsync/DB transaction/別process間のdurabilityを検証したものではない。SQLite/D1を採用決定していない。

## テスト

Python: 既存58 + ledger43 + guard7 =108 PASS。
Node: 既存37 + guard4 =41 PASS。
今回新規50件、合計149件。production/PR15のrenderを含む全suiteは今回実行しない。既存readiness parityとsandbox mock testsは全てguard内で実行する。

## 再実行手順（sandbox Linux/CIだけ）

`gcc -shared -fPIC -O2 -Wall -Werror readiness/guard/native_guard.c -o <temp>/plm-offline-guard.so`

4 flagsをtrue、PLM_GUARD_LIBRARYを上記絶対パスにして `python readiness/guarded_tests.py`。
Nodeは同じ4 flagsとLD_PRELOADを指定して `node --import ./readiness/guard/node_guard.mjs --test-isolation=none --test readiness/guard/test-node-guard.mjs serverless/test-worker.mjs serverless/test-d1-setup.mjs serverless/test-cloudflare-setup.mjs`。

通常のunguarded unittest起動は意図的に拒否する。Windows/WSL/Dockerを使う手順ではない。

## 残るUNVERIFIED / 次工程

- real durable backend、複数process/runnerのatomicity・fsync・復旧。
- actual callback signature/fencing/owner handoff、外部uploadとDB間のambiguous boundary。
- 実AI生成、無料quota、実render、artifact容量/保持と$0保証、1h/24h live接続。
- 元n8n liveの完全同値、manualフォーム再送時のintent_id保持は未接続。

次に安全に進められるのは、fixture script checkpointとledgerを結ぶoffline E2E、invalid/partial generation responseとcallback署名境界のmock検証。外部API・renderは使わない。100+ accountの容量/Actions利用適合/Secrets/quotaは別BLOCKERのまま。

ユーザー操作が必要になるのは実認証・実環境確認・実AI/render/private動画テストを解禁する地点。現在は操作不要で、Cloudflareも凍結を維持する。
