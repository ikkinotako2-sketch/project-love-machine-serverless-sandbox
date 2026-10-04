# Approved fixed generalized behavior test runner

2026-10-04、本人が固定33-step remote behavior testの最終実行を1回承認した。plan raw SHA256 `452fd980ba62164f71cfe3841ea7d399ef988c6e259945d5c67487a44eaf52c7` は変更しない。SQL/params/expected outcomes/changes/trigger tokens/full rows/budgetsをそのまま使用する。

新runnerとapproved workflowはsandbox branchのみ。元のbehavior placeholder workflowと全preflight workflowはhard-disabledのまま。新approved workflowもprepare中はhard-disabled / allow=false / UNAPPROVED。offline CI全PASS後、固定prepare commit pin / push event before / exact activation message / attempt1 / GitHub branch headと全execution historyが一致した1 runだけを有効化する。

送信直前fresh gateは、先のfinal preflight codeを再利用する。固定approved receipt raw SHAを検証し、Behavior Token account verify1回のみでactive/finite expiry、Read Tokenだけでschema/inventory/DB size/bookmark/既存証拠/0-row baselineを確認する。既に消費された以前のpreflight runを再実行しない。今回のapproved execution historyをfresh gateへ渡し、prior behavior execution=0・current uniqueを確認する。migration成功receipt、stage2成功3 row、atomicity row、test_jobs0、_cf_KV schema不変は必須。1条件でも不一致ならmutation0 STOP。

専用mutation transportは `/query` POSTの固定33-step SQL/paramsのみ、順番厳守、各最大1送信、33回上限。Behavior Tokenはverify1回と承認されたmutation経路に限定し、D1監査・read-backにはRead Tokenのみ。各send前にexclusive fsynced SENT journalとsanitized SENT logを作る。個別step再送・run再開禁止。runner1/concurrencyで直列。

各stepの前提は、初回5table全rowが固定before_rows exactであること。正常応答はsuccess/primary/empty errors/results/exact meta.changesを必須とし、expected APPLIED/NO_OPへ分類する。期待拒否はHTTP400または200＋success=false＋errors1件code7500＋exact known trigger tokenのみ。token単体または固定D1_ERROR/SQLITE_CONSTRAINT包装だけを許容し、それ以外の文言は保存しない。unexpected code/status/message/resultはSTOP。各stepの後、5table全rowのprimary read-backと固定after_rowsをexact照合して初めて次へ進む。callback stepのlogical changesはtriggerを含む3。

33 sends最大、成功logical changes18最大。最終job/script/render各1、GENERATION/RENDER/UPLOAD effect各1、callback1、計7 row。他identityは0。UNKNOWNはSQL state simulationだけ。provider/Worker/AI/render実行/YouTube/SNSは0。

mismatch/timeout/ambiguous/unexpected時は即STOP、次mutationなし。retry/resend/fallback/automatic rollback/DELETE/DROP/resetは0。mutation送信があればpost-checkを最大1セットだけ実施し、途中停止時はそれを唯一のread-only reconciliationにする。

post-checkは全既存schema/indexes/証拠、5table全schema/columns/autoindexes、actual row counts、final full rows、fresh bookmarkを検証する。migration用zero-row contractをschema検査だけに投影して再利用し、actual countsを別に検証する（現在のbehavior rowsが0とは主張しない）。FULL_APPLIED/PARTIAL_APPLIED/NOT_APPLIED/STILL_UNKNOWNはtest rowsの状態を示す。SUCCESSには全33steps一致、18 logical changes、fixed final rows、preservation/schema/fresh bookmarkの全PASSが必要。

sanitized receiptには固定fixture rowとexpected outcome、bounded error code/safe trigger token、照合結果だけを保存。Token、signed URL、raw headers/provider body、untrusted exception textを保存しない。結果にかかわらずworkflowをhard-disabled / allow=false / UNAPPROVEDに戻しread-back。live_ready=false / posting_permitted=false / 4安全フラグtrueを維持する。

最後に本人へCloudflare `plm-sandbox-d1-roundtrip-behavior-once` Token失効/削除＋GitHub Secret `PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN` 削除を要求する。`PLM_CF_D1_READ_TOKEN`維持。既存stage2証拠と今回のrowはDELETE/resetしない。production / sandbox main / n8n / V1 / 既存YouTube Pipeline / PR #15/#16変更禁止。

公式query API: https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
