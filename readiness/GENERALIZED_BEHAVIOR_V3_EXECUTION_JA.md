# V3 固定33-step実行境界

本人の最終承認はidentity `rt-behavior-20261004-003` とplan raw SHA256 `ecfa8fc1590f3cc705a4b87bc8f935d9a21f7b592e8474eab2128ec1e79117e2` の1回限り。旧2 run/identityは永久consumedで保持する。

実送信直前にV3 Tokenをverify最大1回（active/finite expiry）、D1監査をRead Tokenだけで行う。固定plan/oracle/receipt、schema SQL/hash、inventory、旧2 ACTIVE job、全既存証拠、新identity不存在、prior execution=0を照合する。不一致ならmutation 0で停止。verify APIはToken scopeを独立証明しないためowner registration evidenceとして扱う。

閉じたtransportは固定順SQL/paramsだけを最大33回送信する。各step前後に全5 tableのprimary read-backとexact schema/hashを照合。16 APPLIED /17 NO_OP、logical changes最大18（callbackはtriggerによる3changes）、新規最終rows最大7。intentional ABORT=0。7500を含む全エラーはSTOP。message parserを成功条件に使用しない。

`changes=0`はclient SQL predicate no-opの証拠。trigger/immutable invariantはremote exact schema/hash + offline exact-SQL oracle17件の証拠であり、役割を混同しない。

timeout/unknown/API error/changes/state/schema mismatchでは次mutationを送信せず停止。read-only reconciliationは最大1セット、resume/retry/resend/fallback/rollback/delete/resetは禁止。receiptは固定rows、hash、codeと固定安全messageだけを保存し、Token/headers/raw provider bodyは保存しない。33/33とfinal rows一致・既存証拠不変・fresh bookmarkを満たす時だけSUCCESS。

実行後はworkflowをhard-disabled/allow=false/execution_approved=falseへ戻しread-backする。Worker/AI/render/YouTube/SNS/external providerは0。Geminiへ進まない。結果に関わらずV3 Tokenと対応GitHub Secretの失効/削除を本人に要求し、Read Tokenは維持。

## 実行結果

run `37173135193` は SUCCESS。33/33全stepの固定SQL/params・before/after rows・schema/hash・primary response・expected changes一致。送信33、logical changes18、APPLIED16、client predicate no-op17。final stateはjob1/script1/render1/effects3/callback1の新規7row exact一致。jobはowner_b/epoch2/fencing2/version4/SUCCEEDED、UPLOADはCONFIRMED。final rows SHA256 `ffefa49a6ec79ba36cfed92963f566b0b2a65fdb53800788f2bd8e634f8dd86c`。

fresh gateはV3 Token verify1/active/finite expiry、Read Token audit39、prior V3 execution0、新identity全5table0、旧2ACTIVE job exact不変、全既存証拠・schema/hash・inventory exact一致。実行中とpost-checkのRead Token callは441。reconciliation0、normal post-check1。Token scopeはowner registration evidenceでありverify APIによる独立証明ではない。

fresh final bookmark `00000026-00000020-000050fa-014af190ea61f59d525727e0a9339b41`。旧2ACTIVE job、stage2成功3row、atomicity row、test_jobs、_cf_KV schema、既存schema/index/triggerは不変。_cf_KV contentは仕様上対象外（NOT_APPLICABLE_RESERVED_UNQUERYABLE）。

offline CI `37173082750`: Python488 + Node939 = 1427 PASS /0 FAIL、exact-SQL negative oracle17件を含む。immutable sanitized receipt: `audit-evidence/generalized-behavior-v3-approved-result-37173135193.json`。実行workflowはhard-disabled/allow=false/execution_approved=falseへ復帰しremote read-back exact一致。全3identityとrunは永久consumedで再利用禁止。

retry/resend/fallback/automatic rollback/DELETE/DROP/reset=0。Worker/AI/render execution/YouTube/SNS/external provider=0。live_ready=false/posting_permitted=false/4安全フラグtrue。Token/headers/raw provider bodyはreceiptへ保存しない。本人へCloudflare `plm-sandbox-d1-roundtrip-behavior-v3-once` Token失効/削除とGitHub Secret `PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V3_TOKEN` 削除を要求して停止する。Read Tokenは維持。
