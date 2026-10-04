# Step3 code7500解析とoffline修正版

旧run `37167246069` は **PARTIAL_APPLIED / 永久consumed**。resume/retry/resend/reset/deleteは禁止。旧identity `rt-behavior-20261004-001` と残存ACTIVE jobは監査証拠として保持。旧receipt、旧plan、旧runner、migration SQLは変更しない。Behavior Token cleanupは本人確認の別証跡に保存し、旧receiptのcleanup欄を改変しない。

## 確定事項と限界

| 仮説 | 結論 | 根拠 |
|---|---|---|
| trigger自体の不具合 | exact SQLでは再現せず | D1 receiptの `plm_rt_v1_job_guard` SQLが固定after schemaと一致。exact migrated SQLのSQLite fixtureでWHEN=1、RAISE ABORTのtokenとerror1811を確認。全rows不変 |
| D1/SQLiteの意味論の差 | この証拠からは確認できない | remote7500はSQLite extended code1811そのものではない。remote messageは保存されていない。remoteの実際のerror種別・wrapperは復元できない |
| runner message parserの過剰制限 | 設計上の制約を確認、STOP直接原因はmessage認識gate | v1はtoken単体/D1_ERROR prefixと固定SQLite suffixの6全文字列形式だけを許可。step3診断はsafeTrigger=null相当のREDACTED。公式REST APIはmessageをstringとして定義し、この6形式を保証しない |

**特定のCloudflare wrapperが原因だったとは断定しない。** raw message未保存のため「v2なら旧step3が確実にPASSした」とも主張しない。確認できたroot causeはRUNNER_MESSAGE_RECOGNITION_GATE_FAILED。v2候補のremote適合性は新identityで別承認後に検証が必要。

run code pin `3c7171d8469b0cd91b1f5c32e37cf1c221d7aff1` のrunner/entryをGitHubからread-only取得し現在の旧ファイルとexact照合。raw SHA一覧を別source-proofへ保存。

旧plan raw SHA `452fd980ba62164f71cfe3841ea7d399ef988c6e259945d5c67487a44eaf52c7`、migration SQL raw SHA `45f042a1342676ceeeed587490d80eb132e31a2c3d9b33cceeab3045ffdf37b5`、old receipt raw SHA `3ca60a6834b4bbbe3f53e9eeed63a060771fea5958c56f6d3937ea2b1709ebdd` を照合。

step1 APPLIED/changes1、step2 duplicate NO_OP/changes0。step3 SQLはintent_id変更、version+1、updated_at+1、job_id固定のUPDATE。対象jobは存在し、`NEW.intent_id IS NOT OLD.intent_id` がtrueなのでWHENは確実に成立する。guardの同owner ACTIVE→ACTIVEは許可されたstate transitionにも該当しない。exact migrated predicateをOLD/NEW CTEでも評価しWHEN=1を確認。SQLite fixtureでtoken=`rt_job_fence_or_transition` / extended error1811 / 全5table before-after不変を再現。

step3直前rows（step2 full read-back）、固定plan step3.before_rows、step3後read-only reconciliation rowsはcanonical全列exact一致。旧job owner_a / epoch1 / fencing1 / version1 / ACTIVE。他4table0。

## 公式error envelopeとの比較

Cloudflare REST query APIはerrors[].codeとerrors[].message(string)を返す。messageの全文字列を6形式へ限定する仕様はない。D1 debug資料にはD1_ERROR/D1_EXEC_ERRORと詳細contextを含む例があるが、Worker exec例であり、旧REST responseの実際のwrapperを証明しない。SQLite公式RAISE(ABORT)は指定messageとSQLITE_CONSTRAINTを返しstatementをabortする。

公式資料:
- https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
- https://developers.cloudflare.com/d1/observability/debug-d1/
- https://www.sqlite.org/lang_createtrigger.html

## v2 parser候補

`generalized-behavior-safe-trigger-v2.mjs` を新設し、旧runnerへは導入しない。固定migration RAISE token12個だけをallowlist化。messageは最大160 printable ASCII文字。whole identifierとしてrt_を含む候補が**1出現のみ**、exact allowlisted tokenであることが必要。同じtoken2回も、別token併記も拒否。prefix/suffix substring、未知token、Unicode/control/oversizedを拒否する。

一意tokenを抽出した後も、boundedなSQL error-cause wrapper grammarを必須にする。単なるtoken言及・SQL literal・authorization/syntaxなど別error文言は拒否。HTTP200/400＋success=false＋errors1件＋code7500＋empty/no result＋expected token exactを全部必須。code7500だけでは絶対にPASSしない。次stepにはfull primary read-backの不変確認も必要。

保存するdiagnosticsはcode＋allowlisted tokenまたはredacted固定message、固定reason enumのみ。原文やprefix、raw body、headers、Token、signed URLは保存しない。新しいwrapperの例はsynthetic test fixtureであり、旧実responseを復元したものではない。

## 新identity固定plan候補

`generalized-behavior-v2-test-plan.json` raw SHA256:
`9d1fa88573219b5f90bdd50a90045b9b73229fd7041a79c48ddb09b38c120a1d`

新identity `rt-behavior-20261004-002` / account `youtube_synthetic_rt_002` / intent `private-roundtrip-behavior-20261004-002`。旧identityをparamsへ使わない。33steps / mutation sends最大33 / successful logical changes最大18 / runner1、新job/script/render各1、GENERATION/RENDER/UPLOAD effect各1、callback1。新規最終7rows。全before/after/global final rowsには永久保持旧jobも含むため、最終job tableは旧1＋新1＝2行。他identity作成なし。

既存stage2/atomicity/test_jobs/_cf_KV schema、旧ACTIVE row、migration4SHA、oldreceiptをprotected baselineとして固定。oldrun再開禁止を明示。新planとv2 workflowはallow=false / execution_approved=false / hard-disabled。新execution runnerは未作成。全33stepのoffline SQLite replayで新plan18changesと旧job不変を検証する。

今回のfresh Read Token auditは新たな本人依頼の根拠確認であり、旧run reconciliationを再試行するものではない。READ tokenだけで全schema/columns/indexes/既存証拠/残存rows/inventory/DBsize/freshbookmarkを確認。D1 mutation/write、Worker、AI、render、YouTube、SNS=0。

全offline CIとread-only baselineがPASSしたら、新identity remote検証に必要な本人操作は1つ: `plm-sandbox-d1-roundtrip-behavior-v2-once` をD1 Edit/Writeのみ・短い有限TTLで作成し、GitHub Secret `PLM_CF_D1_ROUNDTRIP_BEHAVIOR_V2_TOKEN` に登録する。登録は実test承認ではない。Token登録後もfresh final read-only preflightと別の最終実行承認までmutation0。

production / sandbox main / n8n / V1 / 既存YouTube Pipeline / PR #15/#16変更なし。live_ready=false / posting_permitted=false / 4安全フラグtrue。旧rowも新candidateもDELETE/resetしない。
