# V2 approved execution result: STOP / PARTIAL_APPLIED

Run 37169509729 (attempt1)、code pin d6c996b90c84900b4b769d155c8d8ecd83f3c293、event a87e86c9c90a2c2d811f6759f15dcf74d4e79b23。固定plan raw SHA256 9d1fa88573219b5f90bdd50a90045b9b73229fd7041a79c48ddb09b38c120a1d。plan / parser / migration / 旧receipt未変更。

実送信直前fresh gate PASS。V2 Token active＋finite expiry、verify1。READ Token39callsでschema FULL_APPLIED / 5tables / 11triggers / 14autoindexes、新identity全5table0、旧ACTIVE job exact不変、inventory exact、旧証拠不変、prior V2 execution0を確認。

Step1 APPLIED / logical changes1 / full readback一致。step2 NO_OP / changes0 / full readback一致。step3 expected REJECTED、code7500、parser reason UNSUPPORTED_OR_UNRELATED_WRAPPER、outcome UNEXPECTED / match=false。診断messageはREDACTED_UNRECOGNIZED_MESSAGEのみ。raw provider body/message/headers/token/signedURLは保存しない。7500だけで成功にしない。

次mutation送信なし。sends3 / confirmed logical changes1 / matched steps2。step4..33 sends0。read-only reconciliation1set / post1set。PARTIAL_APPLIED、schema FULL_APPLIED / preserved=true。step3直前full rowsとreconciliation rowsが全列exact一致。旧ACTIVE job001もexact不変。新job002はACTIVE owner_a / epoch1 / fencing1 / version1、script/render/effect/callback0。job table合計2行（旧1＋新1）。fresh bookmark 00000022-00000002-000050fa-e3714f0d4bbaf03fefbc9e18a2ea03e5。

V2 run/identity002も永久consumed。resume/retry/resend/reset/delete/rollback禁止。旧run37167246069 / identity001の永久consumed扱い維持。どちらもACTIVE証拠として保持する。

HTTP counters: fresh verify1＋fresh READ39、execution READ54、D1 mutation3。retry/resend/fallback/delete/drop/reset/automatic rollback0。Worker/AI/render execution/YouTube/SNS/external provider0。live_ready=false / posting_permitted=false / 4安全フラグtrue。

runner追加offline CI37169455504 PASS: Python488 + Node806 =1294。結果保存後のoffline CIも確認して別証跡へ保存する。workflow hard-disabled / allow=false / execution_approved=falseへ戻し、readbackする。

本人へ要求するcleanup: Cloudflare plm-sandbox-d1-roundtrip-behavior-v2-once Token失効/削除、GitHub Secret PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V2_TOKEN削除。PLM_CF_D1_READ_TOKENは維持。追加remote検証は今回実施しない。production / sandbox main / n8n / V1 / 既存YouTube Pipeline / PR15/16未変更。
