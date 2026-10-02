# 1-account offline統合の再検証 — 2026-10-03 JST

引継ぎ時の基準87%/263testsより後の既存commit `13b76b3038886760e49d07f7da65cc7dfa65022e` に、今回指定された9範囲が実装済みだった。そこで同じ機能を再実装せず、全コードとrunbookを照合しguard内で再検証した。既存CI run 36994888989のログはPython354/Node41 PASSと両runtimeのrender_executions=0/external_api_calls=0を確認できた。

今回追加の修正はread-only Command Center modelのみ。terminal uploadのsuccess後にもmetrics_evidenceを固定表示していた点を直し、slot証拠から1h→24h→Improvement→next-intent候補のレビューへ進む。expected time/deadlineは未収集slotのdurable originから導出し、期限不明のImprovement/レビューに架空時刻を置かない。最後のcheckpointもmetrics/improvement/next-intentに追従する。明示missedはinspect_only、unknownはmanual reconciliation、期限超過pendingをmissedへ変換しない。新規8 regression tests。

ローカルguard検証: Python362 PASS/FAIL0、Node41 PASS/FAIL0、計403 PASS。native seccompのsocket/exec拒否を確認。render_executions=0/external_api_calls=0。GitHubコネクタの読取/commitと公式資料閲覧はoffline test runtimeの外部API件数に含めない。過去のdummy render誤実行2件は既存監査に残り、この0は履歴全体を上書きしない。

進行度は92%を維持。提示基準87%との差+5ptは既存完了commitの回収を含み、この会話で新たに5pt実装した意味ではない。今回の再検証による進行度追加は0pt。残り実作業6–12時間は従来概算を維持、remote backend実装/障害検証次第で増える。認証/承認待ちは未定、実private投稿後の1h/24h待ちは別計上（70分/約24h＋実行遅延）。100+accountsは別BLOCKER。

## 保護対象の再照合

production mainは現在 `ccebeefc694e37ef01e6f88cd23a9a2b79872894`。過去のpinned `fd4cd8b1f714d1c5ccffbabe88b89b64e36b468b` から進んでいるが、render-short/youtube-pipeline/youtube-adapter/youtube-metrics-1h/youtube-improvement/command-centerの6workflowを読取り、全てfinal_sources.jsonのSHA256と一致した。productionは変更していない。

PR15/16はDraft・未merge、headはfinal_sources.jsonの値と一致。n8nは操作せずexportの責務分類を維持、live状態はUNVERIFIED。Cloudflare凍結。4安全フラグtrueを維持。Secret登録/読取りなし、API/render/FFmpeg/Docker/VOICEVOX/投稿/production dispatchなし。

## Google公式資料の再照合

2026-10-03 JSTにmodels/pricing/rate-limits/structured-output/GenerateContent structured-outputを再読した。

- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/structured-output
- https://ai.google.dev/gemini-api/docs/generate-content/structured-output

3.8 Flash/3.5 Flash-Liteは公開model候補。3.8 FlashのStandard pricingには無料input/outputの記載があるが、個別projectのmodel可用性や無料quota保証ではない。RPM/input TPM/RPDはproject単位、RPD resetはPacific midnight。実active quotaはAI Studioで確認する必要がありUNVERIFIEDを維持。

current structured output guideはInteractionsのresponse_format、Legacy GenerateContent guideはgenerationConfig.responseFormat.text.mimeType/schemaのREST例を掲載。現在のdata-only proposalは後者と一致し、前者のresponse shapeとは混同しない。JSON Schema subsetだけで意味や品質を保証できないためstrict local validatorは維持。API referenceページの今回の閲覧はInternal Errorで取得できなかったので、今回そのページを再確認済みとは扱わない。実provider受理/SDK compatibility/品質はUNVERIFIED。

18項目gateとn8n parity表はFINAL_OFFLINE_READINESS_JA.md、全段階STOP/PASS/rollbackはLIVE_MIGRATION_RUNBOOK_JA.mdにある。offline_complete=true、live_ready=false、posting_permitted=falseを維持。実DB/複数process atomicityはreference interleaving/threadsで代用してPASSにしない。公開HMAC fixture keyは実認証ではない。

最初のユーザー操作は将来のCloudflare凍結解除の明示指示とsandbox専用read-only認証を保護入力欄へ登録すること。今は実操作を要求しない。段階10 TEST_ONLY往復もEmergency Stop=trueのままではBLOCKED。
