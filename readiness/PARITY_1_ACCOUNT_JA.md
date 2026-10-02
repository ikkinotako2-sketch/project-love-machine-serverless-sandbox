# 1-account YouTube offline parity — 2026-10-02

判定: offline fixture比較はPASS。全自動化全体はPARTIAL。実AI、render、投稿、Cloudflare migration/deploy/callback/live jobは本工程の対象外。

## 確認した実物

- production main `c869b41f941b9cdff45cd2ceb16532de777b6ac1`: Improvement `validate_ai`、YouTube Pipelineのworkflow_dispatch入力18項目、rendererへの受渡し。
- Draft PR15 `a3bad01929b0db39499b4320182068f7a7e0047d`: ClaimStore/SQLiteのowner+version CAS、initialize前の状態保存、unknown時の再initialize禁止。変更していない。
- Draft PR16 `e5ad13c1a92bf390272ce2c547f6b5ecaf8caa9c`: TEST_ONLY制御。変更していない。
- ローカルのV2 export: `Code in JavaScript2`、`後続処理用に整形`、`Cloud Render Payload`、`Trigger GitHub Render`。exportのactive値からlive状態は判定しない。
- export、Pipelineのハッシュと上記SHAは `parity_sources.json` に記録。必要なpure code/式と入力schemaだけを抽出し、credentials/headers/接続情報は含めない。

## 6工程の実装と証拠

| 工程 | 実装・検証 | 境界 |
|---|---|---|
| Improvement 7項目 | hook/duration/caption_density/scene_changes/narration/cta/topic_selection。生成側は完全一致7keys、各1–180 Python文字、analysis<=250。production関数oracleと比較 | 生成側では空白や改行を禁止していない。この仕様を勝手に変更しない |
| V2受取 | status ready、HTTP成功、各必須key、空白だけ不可、JS UTF-16で<=240、制御文字不可。余分なkeyは既存どおり許容 | malformed/unavailable feedbackは空guidanceで通常処理を継続。AIは呼ばない |
| 台本整形 | outputからtitle/hook/narration/scenes/bgm、字幕index=1始まり・start_seconds/end_seconds/text | valid schemaのJSON fixtureのみ。n8n全ランタイムの型変換はUNVERIFIED |
| renderなしE2E | theme fixture→script fixture→正規化→renderer payload→Pipeline入力比較 | scriptは固定fixture。themeからのAI生成や音声時間整合は未検証 |
| monitor | pending / deadline_exceeded / missed / unknown / collectedを区別 | missedは既存collector等の明示的証拠が必要。期限だけでmissedにしない。unknown自動再送なし |
| Pipeline contract | 18項目名・型・choice・boolをpinned YAMLと照合、V2 dispatch式oracleと全値比較 | dispatchしない。安全4flagsは別envelopeで保持し、本番inputsへ勝手に追加しない |

`n8n_parity_oracle.mjs` は抽出したpure式を実行する比較用コード。production/n8nへ接続しない。`parity_fixture.json` の期待値も、この独立oracleから作成した。

既存scaffoldの字幕キーを実V2と一致させ、`youtube_game_001` を許容した。動画生成は行わない。

## Manual / Schedule の共通入口設計

現在のV2はmanual Formがqueue claimを迂回する。これは実物の差であり、既存構造を「既に共通claim」と評価しない。

移行先では、双方を同じ `PublishIntent` 正規化とdurable claim入口へ通す。ManualとScheduleはsource属性だけが異なる。

1. account固定・platform youtube・themeを正規化。Manualは利用者が生成したsubmission identity、Scheduleは保存されたqueue row identityとoccurrence identityを用いる。任意のフォーム値やtheme本文だけを冪等キーにしない。
2. ledgerに `(platform, account_id, intent_id)` を一意保存し、job_idを一度だけ割り当てる。retry/再開で作り直さない。既存V2の `yt-<execution id>-<millis>` は初回mint時のみ使う想定。job fixtureは同じ形式。
3. 台本を一度生成できた時点でcontent fingerprintとimmutable payloadを保存する。再試行で台本を再生成して同じjobへ上書きしない。同一jobの異なるfingerprintは拒否。
4. 同じ `(platform, account_id, job_id)` のdurable atomic claimを取得。owner/versionのCASが必要。ManualにもScheduleにも必須。
5. upload開始前のdurable状態を保存。外部APIとの単一transactionは成立しない。応答喪失・unknown・初期化途中はreconciliation only。time-based takeover、自動再投稿は禁止。
6. succeededはterminal/no-op。YouTubeに保存済みvideo_idがあれば照合のみ。owner移管には旧workerの停止証明とfencingが必要。

本工程のE2Eは同じjob/contentを与えたManual/Scheduleの入力・fingerprint一致を検証するだけで、durable ledger/claimを実装・本番接続したものではない。PR15はTikTok専用contractであり、YouTubeへそのまま流用したと扱わない。SQLite本番採用は未決定。

## monitorと既存collectorの関係

既存Improvement `due_slots` は1h/24hに対し許容遅延3h/36h、attempts>=3ならfailed、collected/missed/failedをskipする。本monitorはその処理を変更せず、結果を読む監視モデル。

deadline_exceededは監視上の警告であり、collectorが書いたmissedとは別。unknownは応答不明のまま保持する。collectedは期限超過後もcollected。1h/24hは独立し、欠測値を0として捏造しない。ネットワーク検証/collectorへのwrite/retryは行わない。

## 公式資料の照合

確認日2026-10-02。GitHub workflow syntaxとREST workflowsは25 inputs上限を一致して示す。workflow syntaxの65,535文字とbool型を参照し、18入力のfixtureを検証。API受理そのものはUNVERIFIED。

- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://docs.github.com/en/rest/actions/workflows

Gemini structured output docs（更新2026-09-23）とgenerateContent APIを照合。JSON Schemaはsubsetであり、application側の値検証が必要。現在のn8n parser/実モデル/Free quotaとのlive互換性はUNVERIFIED。新モデルへの切替やAPI clientは追加しない。

- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/api/generate-content

YouTube videos resourceとvideos.insertを照合。privacyとaudience/altered synthetic declarationは別々の項目。fixture内falseは既存V2の比較用defaultであり、実動画の正しい宣言を確定したものではない。private指定も投稿許可にはならない。

- https://developers.google.com/youtube/v3/docs/videos
- https://developers.google.com/youtube/v3/docs/videos/insert

## テストと制約違反の記録

- 新規36 + 既存readiness22 = Python58 PASS。既存sandbox Node37 PASS。CIも同じスイートを実行する。
- production snapshotの非render57、PR15 snapshotの非render100 PASS。両者は重複する既存テストを含むためユニーク件数ではない。
- 実行前の選別を誤り、既存全スイート58/101の各1件 `test_real_render_and_quality_gate` が3.2秒ダミー動画を生成した。合計2回のローカルdummy renderは今回のrender禁止への違反。TemporaryDirectoryは終了時削除済み。SNS/AI通信・投稿はない。再確認時はこの1件を各suiteから明示除外した。production/PRのコード変更はない。今後この作業ではrender testを実行しない。

## 1-accountで残る工程

1. offline: malformed script/型変換範囲の追加fixture、generation request/response境界の固定、common-entry ledger/recoveryシミュレーション。
2. live開始前: 本人のaudience/AI宣言確認、1-accountの無料AI quota、artifact実容量/保持期間/課金防止設定を確認。
3. durable storageと所有権/fencingの実装・障害試験。Cloudflare認証は凍結中の別blocker。
4. 明示承認後だけ、段階ごとの実AI→render→private動画1本テスト。現在は全て禁止。

100+ accountsのstorage/GitHub用途適合/YouTube quota/Secrets隔離は別スケールBLOCKERとして維持し、1-account offline作業を止めない。PC常時稼働やWindows/WSL/Docker Desktopは前提にしない。

Cloudflare migration/deploy未実施、callback/live job 0、安全4flags true。main/PR15/16/n8n成功経路は変更なし。実API・AI・render・投稿へ進む前に停止する。
