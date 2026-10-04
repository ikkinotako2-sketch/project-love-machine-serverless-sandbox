# Generalized backend SQL behavior候補

Sandbox branch `plm-offline-readiness-v1-20261002` のみ。実test承認なし。D1 mutation/write、Worker、AI、render実行、YouTube、SNSはすべて0。live_ready=false / posting_permitted=false、TEST_ONLY / DRY_RUN / NO_PUBLISH / EMERGENCY_STOP=true。

固定plan: `serverless/generalized-behavior-test-plan.json`。raw SHA256は `452fd980ba62164f71cfe3841ea7d399ef988c6e259945d5c67487a44eaf52c7`。`serverless/generalized-behavior-plan-sha.json` と独立hardcoded contractで一致必須。33 step、mutation sends最大33、successful logical row changes最大18、runner 1。最終rowはjob/script/render各1、GENERATION/RENDER/UPLOAD effect各1、callback1、合計7。既存stage2証拠3 rowは永久保持。

| Step | 検証 |
|---|---|
| 1–3 | job作成、同一identityのexplicit unique-intent conflict target no-op、identity変更拒否 |
| 4–6 | owner_a→owner_b成功、epoch/fencing各1→2、version CAS、stale owner/fence 0-change |
| 7–10 | script STARTED、開始後handoff拒否、completed scriptなしのRENDER reservation/artifact拒否 |
| 11–15 | GENERATION RESERVED→SENT、effect開始後handoff拒否、stale owner/fence 0-change |
| 16–17 | synthetic script JSONのexact bytesとSHAをdurable保存、generation CONFIRMED |
| 18–21 | RENDER RESERVED→SENT、synthetic artifact fingerprint/SHA/ref/quality PASS保存、render CONFIRMED |
| 22–26 | UPLOAD RESERVED→SENT→UNKNOWN、job UNKNOWN、UNKNOWN→SENT再送拒否 |
| 27–29 | UNKNOWN中再reservation拒否、stale callback epoch/fence拒否 |
| 30–33 | callback挿入＋upload CONFIRMED＋job SUCCEEDED atomic 3 changes、exact duplicate no-op、payload/account conflict拒否 |

全SQL/params、全step before/after generalized rows、final rows、全stepで同一のprotected before/after既存rows、固定schema4 SHAとmigration receipt SHAをplan内に保存する。fixtureは `rt-behavior-20261004-001` / `youtube_synthetic_rt_001` の1 identityだけ。unique intentの検証にも別jobを作らない。invalid conflict値は拒否される入力のみで、第二identityは保存しない。

D1公式APIでは `meta.changes` はSQLite `sqlite3_total_changes()` に基づく。callback triggerによる3 changesを含む。`rows_written` はindex書込も含むためlogical changes予算には使わない。
公式資料: https://developers.cloudflare.com/api/resources/d1/subresources/database/

成功/no-opはexact meta.changes、各step後の5table全primary readback、固定after_rowsをすべて満たした場合だけ次へ。期待拒否はboundedな既知trigger tokenだけに限定し、エラーcodeと安全な最大160文字messageのみ保存、primary readbackがbefore_rowsとexact一致して初めて次へ。未知code/message、timeout、不明response、mismatchは次mutationなしSTOP。read-only reconciliationは最大1セット、以後停止。SQL stateとしてのUNKNOWNは予定されたsimulationであり、HTTP unknownへの継続を許可しない。

DELETE / DROP / reset / retry / resend / fallback / automatic rollback=0。SQLによる拒否検証はprovider再送ではない。実provider通信なし、生成・artifact・upload resultは明示synthetic。SHA correspondenceはcaller/offline replayで検証する（DBがSHAを計算するとは主張しない）。将来実upload時もprivate固定、notifySubscribers=false。現段階はrender workflowや外部adapterを呼ばない。

Read-only preflightはREAD secretだけを参照し、閉じたSQL allowlistで34 Cloudflare read calls（通常inventory1page）。5 tables / 11 triggers / 14 autoindexes、全row0、stage2 rows/atomicity/test_jobs/_cf_KV schema、既存schema/indexes、inventory、DB size 196608 bytes、fresh bookmark、migration receipt、4 migration SHA＋plan SHA、GitHub全execution historyを確認する。_cf_KV内容はNOT_APPLICABLE_RESERVED_UNQUERYABLE。失敗の自動再試行なし。

実test workflowはhard-disabled / allow=false / UNAPPROVED、secret参照なし、mutation runner未実装。preflightに対してのみprepare commit pin＋event before＋exact push message＋attempt1＋branch head＋全履歴unique runのgateを設ける。preflight終了後にそのworkflowもhard-disableしread-backする。

全PASS後の本人操作は1つ: `plm-sandbox-d1-roundtrip-behavior-once` をD1 Edit/Writeのみ・短い有限TTLで作成し、GitHub Secret `PLM_CF_D1_ROUNDTRIP_BEHAVIOR_TOKEN` に登録する。登録は実test承認ではない。登録後はToken verifyを含むfresh read-only gateを行い、別の最終実行承認までmutation 0を維持する。

production/main/n8n/V1/既存Pipeline/PR #15/#16は変更しない。migration成功receiptは改変せず、backend credential cleanupは別のowner-confirmed evidenceに保存する。
