# V3 固定33-step実行境界

本人の最終承認はidentity `rt-behavior-20261004-003` とplan raw SHA256 `ecfa8fc1590f3cc705a4b87bc8f935d9a21f7b592e8474eab2128ec1e79117e2` の1回限り。旧2 run/identityは永久consumedで保持する。

実送信直前にV3 Tokenをverify最大1回（active/finite expiry）、D1監査をRead Tokenだけで行う。固定plan/oracle/receipt、schema SQL/hash、inventory、旧2 ACTIVE job、全既存証拠、新identity不存在、prior execution=0を照合する。不一致ならmutation 0で停止。verify APIはToken scopeを独立証明しないためowner registration evidenceとして扱う。

閉じたtransportは固定順SQL/paramsだけを最大33回送信する。各step前後に全5 tableのprimary read-backとexact schema/hashを照合。16 APPLIED /17 NO_OP、logical changes最大18（callbackはtriggerによる3changes）、新規最終rows最大7。intentional ABORT=0。7500を含む全エラーはSTOP。message parserを成功条件に使用しない。

`changes=0`はclient SQL predicate no-opの証拠。trigger/immutable invariantはremote exact schema/hash + offline exact-SQL oracle17件の証拠であり、役割を混同しない。

timeout/unknown/API error/changes/state/schema mismatchでは次mutationを送信せず停止。read-only reconciliationは最大1セット、resume/retry/resend/fallback/rollback/delete/resetは禁止。receiptは固定rows、hash、codeと固定安全messageだけを保存し、Token/headers/raw provider bodyは保存しない。33/33とfinal rows一致・既存証拠不変・fresh bookmarkを満たす時だけSUCCESS。

実行後はworkflowをhard-disabled/allow=false/execution_approved=falseへ戻しread-backする。Worker/AI/render/YouTube/SNS/external providerは0。Geminiへ進まない。結果に関わらずV3 Tokenと対応GitHub Secretの失効/削除を本人に要求し、Read Tokenは維持。
