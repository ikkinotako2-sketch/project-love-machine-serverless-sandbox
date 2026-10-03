# 1-account YouTube private roundtrip readiness — 2026-10-03

今回はread-only D1 auditとoffline準備のみ。live_ready=false、posting_permitted=false、TEST_ONLY/DRY_RUN/NO_PUBLISH/EMERGENCY_STOP=true。AI/Worker/render/YouTube/SNS/D1 mutation=0。production/main/n8n/V1/PR15/16変更なし。

## 保存する証跡

stage2 SUCCESS run37128618965、固定plan SHA230c1acee56c3be8a68cac3c29341675a67cc43d926f2047926982510fdc65b7。元receiptを変更しない。cleanupは本人確認として別receiptに保存し、独立したSecrets一覧確認とは区別する。新read-only auditはschema・columns16/11/9・indexes8・既存atomicity成功row/test_jobs0/_cf_KV schema・inventory exact・fresh bookmarkと最終3rowを照合する。DELETE/reset禁止。

既存migration-empty classifierは新table0行を前提とするため、behavior後の1行をSTILL_UNKNOWNとする。今回はschema exactと最終row exactを別gateで確認し、schema_classification=FULL_APPLIEDとする。過去receiptのclassifierを書換えない。

## Backendの残gap

stage2 schemaはtest_reference_001、固定job/intent/effect/delivery/result ID、fixture://stage2/generation.jsonをCHECKで制限する。実youtube_game_001用には使用不可。checkpointはhash/refのみで実台本を保存しない。既存3rowをそのまま保持し、別一般化backendが必要。

0006_youtube_checkpoint_proposal.sqlは独立tableへの実script JSON+SHAとSTARTED→COMPLETED/UNKNOWNのimmutable保存を示すoffline案。remote適用済みではない。intent uniqueness、owner lease/epoch/fence、request SENT-before-send、render/upload各effectのCAS予約、callback認証・atomic消費、runner crash後のUNKNOWN保持を含む一般化job/effect backendはまだ必要。migration manifest/raw SHA/有限HTTP budget/既存schema不変gateと別の最終承認を用意するまでD1 Writeを使わない。

## 実装接続差分（production snapshot 81f74b8c5da450fdebb31cc76d3f8f9592fde5d9）

| 境界 | 現在 | readinessで必要 |
|---|---|---|
| generation_contract.py | データのみGenerateContent request/厳格parser、quotaはfixture | 専用Free project/model entitlement/残quota/credential制限の非secret証跡、send前durable STARTED |
| checkpoint_e2e.py/intent_ledger.py | local snapshotで台本を保存、checkpoint_inputsでJSON文字列へ写像 | D1 commit完了後に同jobのscript JSON+SHAをRead-backし一致。local snapshotだけでrenderを許可しない |
| youtube-pipeline.yml | initializeがplm-resultsへprocessingを書き、render→adapter→result、workflow_dispatchのみ | 既存Pipelineを今dispatchしない。checkpoint/fencing/SENT/UNKNOWNと接続されていない。将来sandbox wrapperに境界追加が必要 |
| render-short.yml | workflow_call可能、render_id/9個のcontent入力、VOICEVOX/FFmpeg、artifact rendered-short-ID、retention1日 | この既存workflowを再利用。別rendererを作らない。commit固定、payload hash、Quality Gate結果、artifact run/id/hashをdurableに結合する |
| youtube-adapter.yml | privateがdefaultだがpublic/unlistedも選択可、Secrets inherit、30日artifact claim | wrapperでprivate/notify=false/scheduled_for空を固定。artifact claimだけをdurable authorityにしない。1 account/1 jobに固定 |
| youtube/api.py | resumable init+PUT、upload_resume_attempts=3、例外時status回復・sleep・再開 | 現adapterをそのまま安全要件適合としない。production変更禁止のままsandbox専用transport seamで自動再送0を検証する必要。attempts=1だけでは回復status通信を0にできない |
| result/callback | GitHub result artifact/branchでn8nが取得 | 証跡取得は維持できるが、認証済callbackとD1 terminal CAS連結が未実装 |

productionの取得したsourceはPRIVATE_ROUNDTRIP_SOURCE_AUDIT_20261003.jsonに非secretコードのみ保存。変更・workflow dispatchは0。cross-repo workflow_callはrender workflowをpinして使う設計だが、callee checkoutがcaller repositoryを使う点を解決する必要あり。renderer依存の既存snapshot再利用/配置をsandboxで準備し、callee/checkout/code pin同一性を検証する。単にcross-repo usesを置くだけでは完成しない。

## Provider/model/project/無料条件

予定provider Google Gemini Developer API、model gemini-3.8-flash、standard nonstreaming text 1 requestのみ。自動fallbackなし。公式pricingは通常input/output無料枠あり（2026-10-03確認）。実projectのactive quotaは未確認。公開表をproject entitlementと混同しない。RPM/RPD/TPMはproject単位。本人の専用project ID、Free表示、billing未接続、model利用可・残RPD>=1/RPM>=1/入力TPM余裕を非secretで確認。カード登録・Paid tier・billing接続が必要ならBLOCKED。tools/search/maps/batch/cache/media API使用0。free枠で入力がprovider改善に利用され得るためcredentialや私的データをpromptに入れない。

CredentialはAI Studio専用projectのGenerative Language APIだけに制限したauth API keyを将来GitHub Secret PLM_GEMINI_ROUNDTRIP_API_KEYへ本人が直接登録する候補。OAuthやYouTube credentialを兼用しない。新AI Studio keyは現在auth key（service account binding）になる公式仕様。作成者のProject Editor権限はruntimeの広範scope要求ではない。key値はchat/commit/artifact/logに出さず、HTTP header x-goog-api-keyでのみ将来注入する。今は要求・取得・API verifyをしない。

requestはPOST https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent。contents=user text、systemInstruction、generationConfig.responseFormat.text.mimeType=application/json/schema=output_schema、candidateCount=1/maxOutputTokens=4096。現公式GenerateContent API referenceにresponseFormatがあることを確認し、Interactions APIと混ぜない。bounded response<=65536 bytes、STOPの1candidate/1textのみ、厳格な台本validatorを通してtransport metadata/raw bodyは捨てる。診断は固定code/安全bounded messageのみ。timeout/ambiguous/invalid/429/5xxすべて自動retry/resend/regenerate=0、checkpoint失敗時render=0。既存quota_planの6request/day・max3attemptは一般offline試算であり今回の1回計画には適用しない。

公式資料:
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/api-key
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/structured-output
- https://developers.google.com/youtube/v3/docs/videos/insert

## 固定する将来経路（現在は全段allow=false）

1. 一般化backendの実job+generation STARTED/request hashをCAS保存し、1送信をdurable予約。
2. 別の本人AI最終承認後、Gemini GenerateContent1回。timeout/ambiguousはUNKNOWN保存・手動照合、再生成なし。
3. 完全検証したscript JSON+SHAを同job durable checkpointへCOMPLETEDでcommit。Read-back exact一致後だけcheckpoint_inputsでtitle/hook/narration/speaker/scenes_json/captions_json/bgm_json/output_jsonへ変換。
4. render effectを同job/fence/hashで1回予約し、別承認で既存render-short workflowを再利用。render_id=job_id、artifact=rendered-short-job_id。Quality Gate、run ID、artifactとmp4 hashをcheckpointへ保存。曖昧なら再dispatchなし。
5. 別承認と1account OAuth確認後、upload effectをdurable SENT前予約。private固定、notifySubscribers=false、publishAtなし、made_for_kids/contains_synthetic_mediaを本人確認。既存adapter契約を再利用するsandbox transportでinit/PUT各1回、自動再送/再開なし。signed session URLをlog/artifact/D1へ保存しない。unknownなら停止して読取照合だけ。
6. private video ID/statusをReadで確認し、認証済resultをfence付きCASでCONFIRMED/terminal保存。public化/SNS投稿/削除0。

## 次の本人操作を1種類へ限定

最初に必要なcredentialは一般化backend準備用Cloudflare D1 Edit/Write Tokenのみ。専用sandbox account/DB、短い有限TTL、Worker/AI/他resource権限なし。GitHub Secret PLM_CF_D1_ROUNDTRIP_BACKEND_TOKENに本人直接登録。登録はmigration/AI/render/upload承認ではない。登録後もread-only preflightと別最終承認までmutation0。AI/OAuth credentialはまだ依頼しない。実AI前には一般化backend完成・checkpoint remote検証・quota/key証跡・exact request/response offline検証・別AI承認が全て必要。
