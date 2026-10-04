# Step3解析完了・read-only最終結果

旧run 37167246069はPARTIAL_APPLIED / 永久consumed。旧receipt・旧plan・旧runner・migration SQL未変更。ACTIVE job全列を監査証拠として保持。resume/retry/resend/reset/delete禁止。

最新read-only audit run 37168560261はPASS。READ tokenのみ39 read HTTP、D1 mutation/write=0。plm_rt_v1_ schema FULL_APPLIED、5 tables / 11 triggers / 14 autoindexes、旧job1行・他4table0行、stage2成功3row・atomicity row・test_jobs・既存schema/indexes・_cf_KV schema不変。DB size196608。fresh bookmark 00000020-00000000-000050fa-7bd36a9dd2a1a1b2b6e1a47ecf7173a5。新identity002不存在。

exact migrated guard WHEN=1、RAISE ABORT token rt_job_fence_or_transition、SQLite extended code1811、全rows不変。step3直前と旧reconciliationは全列exact一致。STOP直接原因はrunner message認識gate。trigger不具合は再現しない。D1/SQLite差と実message wrapperはraw message未保存のため未確定。

v2 decoderはcode7500だけではPASSせず、一意whole-identifier allowlisted token、bounded error-cause wrapper、expected token、envelopeを検査。multiple-token / substring / oversized / control-char / unrelated7500の拒否testsを追加。旧runnerは変更しない。

新候補identity rt-behavior-20261004-002、raw plan SHA256 9d1fa88573219b5f90bdd50a90045b9b73229fd7041a79c48ddb09b38c120a1d。33step / send最大33 / logical changes最大18 / runner1。旧rowを全before/after/final rowsで保持。新execution runner未作成、workflow hard-disabled / allow=false / execution_approved=false。

Prepare offline CI 37168409449 PASS: Python488 + Node733 =1221。今回の停止commitでも同じoffline CIを再確認する。Worker/AI/render/YouTube/SNS/external provider=0、live_ready=false、posting_permitted=false、4安全フラグtrue。

次の本人操作は1つ: plm-sandbox-d1-roundtrip-behavior-v2-once をD1 Edit/Writeのみ・短い有限TTLで作成し、GitHub Secret PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V2_TOKEN に登録。登録は実test承認ではない。fresh final preflightと別の最終実行承認までmutation0。
