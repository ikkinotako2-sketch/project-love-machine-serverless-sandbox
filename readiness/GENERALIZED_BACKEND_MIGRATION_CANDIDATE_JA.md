# Generalized durable backend migration candidate — 2026-10-04

本人登録PLM_CF_D1_ROUNDTRIP_BACKEND_TOKENはverifyのみ。登録はmigration承認ではない。D1監査はRead Tokenで行う。migration workflowはif:false、allow=false、owner approval=UNAPPROVED。4安全フラグtrue、live_ready=false、posting_permitted=false。

新namespace plm_rt_v1_に5tables/11triggers、columns job13/script14/render11/effect13/callback10、autoindexes14、新row0を作成する候補。CREATEのみ16個、IF NOT EXISTSを使わずcollision時STOP。既存stage2/atomicity/test_jobs/_cf_KV、production/main/n8n/V1/既存Pipeline/PR15/16は変更しない。Stage2 synthetic3rowは監査証拠として永久保存し、DELETE/reset/overwrite禁止。

| table | durable保持対象 |
|---|---|
| plm_rt_v1_job | generic job/platform/account/intent、unique intent、owner/epoch/fence、version/state、旧owner停止証跡、terminal result |
| plm_rt_v1_script | generic checkpoint、provider/model/request SHA、STARTED/UNKNOWN/COMPLETED、script JSON+SHA、owner/fence/version |
| plm_rt_v1_render | artifact ID/ref/SHA、script SHA、render run ID、Quality Gate、owner/fence |
| plm_rt_v1_effect | generation/render/upload各job1件、unique effect/delivery/result、request SHA、RESERVED/SENT/UNKNOWN/CONFIRMED、owner/fence/version |
| plm_rt_v1_callback | unique delivery/callback/result、account/job/fence、payload SHA、consumed timestamp、confirmed terminal |

固定synthetic identityをCHECKしない。platformはyoutube、providerはgeminiに制限するが、account/job/intent/model IDは一般化する。1-account実行時の許可account/modelは将来runnerの固定planで別途制限する。現在は実jobを作らない。

generationはscript STARTED保存→generation effect RESERVED→SENTをcommitしてから将来送信。完全検証したscriptをJSON+SHAで保存してからgeneration CONFIRMED。generation CONFIRMED+script COMPLETEDがなければrender reservationを拒否する。render SENT後のみartifactを保存し、render CONFIRMED後のみupload reservationを許す。UNKNOWN/SENTからRESERVEDへの戻し・effect作り直しは禁止。script UNKNOWNとCOMPLETEDはimmutable。owner handoffは開始前のみ、stop proof+epoch/fence増分が必須、開始済jobの自動takeoverは禁止。

callback insertはcurrent epoch/fence、同account/job、upload SENT/UNKNOWN、render証跡を照合する。AFTER INSERTでupload effect CONFIRMEDとjob SUCCEEDEDをatomic更新、どちらか失敗なら全体ABORT。exact duplicateは固定INSERT OR IGNOREにより0change、異なるpayload/identity/timeはABORT。delivery/callback/result再利用をunique制約で拒否する。

これはdurable格納・順序・fencingのmigration候補であり、外部runner接続完了ではない。D1の組込SHA256演算は使わず、callerがcanonical JSONのSHAと厳格script schemaを検証し、commit後Read-back exact一致を確認する責務を持つ。callback認証署名はSQLでは検証できないので、署名検証前のD1投入を禁止する。artifact_refはartifact://の非secret参照、signed URL/Token/raw headers/raw provider bodyを保持しない。owner stop proofの真偽、外部outbound1回上限、private/notify=false、$0/project quotaは別のrunner gateとして実装・検証する。新backendを一般権限の任意SQL実行に開放しない。REPLACE、破壊SQL、direct table writeへのfallbackをruntimeへ追加しない。

## 固定対象と将来1回のplan

SQL: serverless/migrations/0007_generalized_roundtrip_backend.sql。plan/before/after/hashesはserverless/generalized-backend-*.json。全raw SHAをgeneralized-backend-contract.mjsへhardcodeし、SHA・計画・schema driftはremote前にSTOP。0006_youtube_checkpoint_proposal.sqlは以前のoffline案として保存し、今回適用しない。

将来承認対象の経路はREST /import SQL fileのみ。init<=1、upload<=1、ingest<=1、status poll<=3、side-effect HTTP<=3、import全HTTP<=6、runner1、execution1、/query mutation0。initがcached SQLから直接ingestを開始するprovider仕様もside effectとして扱い、unexpectedなら追加side-effectを送らない。init/upload/ingestのtimeout/ambiguous/unexpectedはその場でSTOP、retry/resend/fallback/resume/automatic rollback0。postcheck/read-only reconciliation最大1set。partial/unknownはschema・rowを保存してSTOP。DROP/DELETE/ALTER既存/rename/reset0。signed URLとraw provider bodyは永続化せず、diagnosticsはerrors[].codeと安全なbounded messageのみ。

preflightはBackend Token active/finite expiryをaccount-owned verifyで確認（scopeはverify responseでは独立証明できない）。Read Tokenでinventory exact、metadata DB size、全既存schema/columns/indexes/rows、fresh bookmarkを取得し、stage2 SUCCESS receiptの最終3rowおよび固定beforeと照合。candidate namespaceは全不存在を要求する。migration実行前にもfresh gateを再度行い、最初のsend前に全page GitHub execution history・消費済journal/receipt拒否を必須とする。今回のpreflightではmigration workflowはhard-disabledかつsecretなし、実行entry自体を提供しない。

全PASSでも実行せず「固定generalized backend migrationを1回だけ実行してよいか」と本人へ最終承認を求める。AI/Worker/render/YouTube/SNSは引き続き0。

## 固定raw SHA256

| file | SHA256 |
|---|---|
| migrations/0007_generalized_roundtrip_backend.sql | `45f042a1342676ceeeed587490d80eb132e31a2c3d9b33cceeab3045ffdf37b5` |
| generalized-backend-plan.json | `59cb7545f1d54976e19d74a2dd08c38987698d0271e1aa1ac6d79b72cc25b9cb` |
| generalized-backend-before.json | `64f4b23b9265bb2f4576b9670241d7afab5f003a5375fca8e8a598aa1a39a468` |
| generalized-backend-after.json | `d77d27b2e14ec333ca5ee4b8aad49c3b99e372e9004acbff3c6425979cb4049d` |

## Fresh preflight結果

Run37162479288/attempt1 PASS。code pin033a71c555222e6c4df592d44d960cd5aadbfbd6、activation796d0ac4b8b569fb39052104e0351094b6011b77。Backend Token verify1回のみ、Read Token監査22回、D1 mutation/write0。active/finite expiry=2026-10-10T23:59:59Z（scopeはverify APIで独立証明不可）。candidate namespace NOT_APPLIED、stage2 schema FULL_APPLIEDと最終3row exact不変。既存schema/columns/indexes/atomicity成功row/test_jobs0/_cf_KV schema不変。inventory exact、DB size102400 bytes。fresh bookmark0000001b-00000000-000050f9-0ef1fb67dade8bc156539f6a1013dcdf。

SQL/plan/before/after raw SHA一致、5table/11trigger/14autoindex、新row0予定。migration execution最大1、runner1、init/upload/ingest各1、poll3、side-effect3/import合計6、query mutation0、retry/resend/fallback/automatic rollback0。unknown時は次side effectを送らずread-only reconciliation最大1setでSTOP。preflight後は両workflow hard-disabled/allow=false/UNAPPROVED。

Offline CI37162426181: Python480+Node544=1024 PASS、fail0、external API0/render0。新規fixtureにはgeneric identity、unique intent、handoff proofとepoch/fence、開始後handoff拒否、unsent response拒否、saved checkpoint後render/upload、unknown不可逆、stale owner/fence、exact duplicate0change、payload conflict拒否、callback effect/job atomicity失敗全体ABORT、既存stage2 row/schema保全を含む。SQLite offline受理はD1 remote migration受理の証明ではない。

証跡audit-evidence/generalized-backend-preflight-37162479288.json。旧success/failure receiptsは変更しない。AI/Worker/render/YouTube/SNS0、live_ready=false/posting_permitted=false/4安全flags trueを維持。本人の別migration承認待ちで停止する。
