# YouTube経路のoffline境界（2026-10-06）

sandbox parent: d9bc6a7e51864d51a561808db26de813d7a14268
production read-only source: b0c7f429a1f58726c4a75f4fb090928cf567b585
sandbox main read-only: 8ac2337a37072ae23f7781e2f47e8dfc7016b30f

004H（run 37403151934、attempt 1）は永久consumed。ffmpeg simulation 1回 rc100、残り0、transaction_proof=false / install_authorized=false。004Iの結論を維持し、未知E:をacceptしない。既存APT evidence・fixture・parser・root10・workflow・markerは変更しない。

## 今回の実装と再利用

`youtube_pipeline_offline.py` はguarded offline tests専用。既存 `one_shot_executor.quality_gate/artifact_gate` と、productionの `build_pipeline_result` のbyte-exact snapshotを再利用する。snapshotのSHA256をテストし、上流commit/blob/SHA256をplanに記録する。古いrenderer source lockを最新productionに勝手に置き換えない。

private・notify=false・scheduleなし・1動画・明示disclosure・OAuth存在・runtime/QG/無料容量確認を要求するdata契約を追加した。QGのサイズと動画digestをupload対象へbindする。ここで使う真偽値はoffline fixtureであり、OAuth・quota・runtimeの実証ではない。live entryは常にBLOCKED。

SQL reference ledgerはkey/job/mediaをuniqueにし、claim成立から永久consumedとして扱う。timeout、cancel相当、unknownでも解除しない。別oracle instanceでも同じDBのclaimを拒否し、前jobの結果未保存なら別jobも止める。既存productionのFAILED再claim・in-memory store・upload resume retryはこの条件に合わない。referenceはmemory DBに限定し、runner消失後の耐久性を主張しない。本番用durable adapterは別途必要。

upload responseは固定keyのみ、private/processed/動画ID/対象digestの一致を要求する。既存builderはok=trueならfailed/unknown/queuedもsucceededとするため、その前に新gateを置く。保存/readback後のみnext_job_readyを返す。error body、exception、secret、raw responseを結果へコピーしない。処理待ちuploaded/queuedも再uploadせずread-only reconciliationで解決する。

## 依存順gate

14項目の具体的証拠・未完事項・依存は `youtube-automation-offline-plan.json` を参照。最初のblockerはAPT未知診断で、source-confirmed完全一致がない。推測でinstall/renderへ進めない。続いて固定Python・VOICEVOX digest/version・speaker・FFmpeg/font・新render markerの承認と実証が必要。

production既存workflowは変更も実行もしない。現状のubuntu-latest/Python minor/cpu-latest/APT install/public-unlisted選択肢/retention30days/error文字列保存/retry3は実起動前に最小overlayが必要。通常offline CIのみ既存workflowで実行する。artifact/cache upload・render・API callなし。

n8nのテーマ/input producerと結果consumerは当面維持し、serverlessへclaim/stage/result/queue guardを移せる設計にする。D1 migration/deployやtimer、dispatchは有効化しない。完全放置のAI台本生成も現行$0 entitlementの証拠がなく、manual fixtureをAI済みと扱わない。

## 承認境界

新runtimeはexact parent/workflow/plan/hash/独立identity/no_retry/no_resumeを準備し、marker作成直前で止める。今回004J runtime candidateもmarkerも作らない。未知E:のsource templateに証拠が得られるまで、新たな同条件runtimeを単に繰り返す価値はない。

初回YouTube実uploadはQuality Gate PASS、1本、新規durable claim、secret存在のみ、private、notify=false、current無料容量を確認して、ownerの明示承認直前で止める。public/unlisted/SNSを許可しない。すべてcloud、PC/WSLなし。今回のruntime effectsは全て0。

## 既存input経路との接続

`youtube_preparation_bridge.py` は既存 `script_to_render`、`parity.normalize_script/render_payload/pipeline_inputs` を通してテーマ・固定台本から既存形式の入力を作る。job IDは既存yt-number-timestamp形式を維持し、account/job/contentで安定したidempotency keyを導出する。provider-neutral checkpointの再利用もテストする。fake QG/private response/result保存まで1つのoffline経路で確認するが、render/uploadの実行実績には数えない。QGはfield whitelistとsecret-like caption拒否を追加した。
