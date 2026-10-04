# Generalized backend behavior read-only preflight result

2026-10-04: **PASS**。実test未実行、D1 mutation/write=0。Worker / AI / render実行 / YouTube / SNS / 外部provider通信=0。

固定plan raw SHA256: `452fd980ba62164f71cfe3841ea7d399ef988c6e259945d5c67487a44eaf52c7`。
33 step / mutation sends最大33 / successful logical changes最大18 / runner1。
1 job / 1 script / 1 render / 各GENERATION・RENDER・UPLOAD effect1 / callback1。最終予定7 row、現在0 row。

Read-only run [37165248542](https://github.com/ikkinotako2-sketch/project-love-machine-serverless-sandbox/actions/runs/37165248542) attempt1、Cloudflare read calls34。Read Tokenだけ、mutation credential参照なし。
- generalized schema FULL_APPLIED、5 tables / 11 triggers / 14 autoindexes exact。
- column counts callback10 / effect13 / job13 / render11 / script14。
- 全5 table 0 row、既存stage2 SUCCESS 3 row exact、atomicity row / test_jobs0 / 全既存schema・indexes不変。
- _cf_KV schema不変、content=NOT_APPLICABLE_RESERVED_UNQUERYABLE。
- inventory exact、DB size196608 bytes。
- fresh bookmark `0000001d-00000002-000050fa-6b2457f533c6a798fad9fc496377c88f`。
- immutable migration receipt raw SHAとSQL/plan/before/after 4 SHA exact。
- GitHub全157 runs / 8 pages確認、過去test executionなし、current run唯一、固定code pin＋event before＋branch head一致。

prepare offline CI [37165207600](https://github.com/ikkinotako2-sketch/project-love-machine-serverless-sandbox/actions/runs/37165207600) SUCCESS: Python488 / Node599 / 合計1087。kernel guardでsocket/exec syscall禁止、API/render0。固定plan33 stepのSQLite replayは全before/after rowsと18 changes、callback atomic 3 changes、既存rows/schema不変を検証した。最終保存commitのoffline CIも完了確認する。

実test workflowはhard-disabled / allow=false / UNAPPROVED / secret参照なし。read-only workflowも単回監査後hard-disableしread-back。live_ready=false / posting_permitted=false / 4安全フラグtrue。DELETE / DROP / reset / retry / resend / fallback / automatic rollback=0。mismatch / HTTP timeout / ambiguous responseでは次mutationなしSTOP、read-only reconciliation最大1セット。

backend Token cleanupは本人確認の別証跡で保存、成功migration receiptとstage2 SUCCESS rowsは改変しない。production/main/n8n/V1/既存Pipeline/PR #15/#16変更なし。

次の本人操作は1つのみ: **`plm-sandbox-d1-roundtrip-behavior-once` をD1 Edit/Writeのみ・短い有限TTLで作成し、GitHub Secret `PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN` に登録する。**

Token登録は実test承認ではない。登録後もfresh read-only preflightでToken active/finite expiryとbaseline/plan/historyを確認し、別の最終実行承認までmutationを送らない。
