# migration後の監査・次の本人操作

対象は1-account用の専用sandboxのみ。production/n8n/V1/既存YouTube/1h/24h/ImprovementとPR #15/#16は変更しない。live_ready=false、posting_permitted=false、4安全フラグtrue。100+ accountsは別BLOCKER。

## 実証したD1状態

Read-only Actions run 37064849312、commit ea00157f55c46a44c8e1950aba9dface218bc003。取得時刻2026-10-03 06:06:56 JST。

- user-owned Read Token active。固定Account 6c8ccd6aface937ab5dabef61cb64534でD1アクセス成功。
- 全inventory取得：1ページ、全1件、他D1 0件。
- DB ID 18050cf6-934e-4f3a-a1cd-5041bac1c35e / plm-serverless-sandbox-state完全一致。
- test_jobsは1テーブル、canonical schema・11 columns・複合primary key・CHECK定義一致、0行。
- _cf_KV定義はmigration前receiptと完全一致。他のテーブルデータは今回読んでいない。
- DB size 20,480 bytes。schema object 2件（Cloudflare内部_cf_KVとtest_jobs）。
- 最新bookmark：00000006-00000002-000050f8-f5a2de6e938ce4dd2b75da1a3fbe5624。
- receipt d1-create-test-jobs-37063527954はmigration run 37063527954 / commit d767ef792a4ca2fe8506c6de2a93ef35354bbefb / 固定SQL SHA ac01f6d9d7eac877b802688d4f1d3c4dd40e8940876ed3ce0dc441c10297d0e2に紐付けた。元run・SQL・履歴を削除/書換えしない。
- 今回Cloudflare API 9回：D1関連read-only 8回、Worker List GET 1回。D1 SQL mutation 0回、deploy/job/render 0回。SELECT/PRAGMAはAPI仕様上POSTでもrows_written=0/changed_db=falseを検査する。

## Write権限の後処理証拠

Cloudflare側Token失効/削除およびAccount API Token一覧0件は本人画面確認をowner evidenceとして記録。失効APIによる独立確認ではない。削除済みTokenを再度verifyするために値を取得/復元しない。

GitHub PLM_CF_D1_API_TOKENの削除はowner evidenceに加え、最新ActionsでSecret式の非空判定=falseを実証。値を環境・ログへ渡していない。Read Token値もログ/commitに保存していない。

migration workflowはif:false、execution-approved:falseに変更。migration-once.mjsは常にHTTP前に拒否するretired entry。歴史的アルゴリズムはmock-only referenceへ保存し、既定fetchを拒否、CLIなし、CIのkernel network guard下のみ検証。履歴commitはそのまま保持。旧run rerunはattempt 2以上を拒否し、現在headへのpushは旧承認SHAとも一致しない。mainの既存setup経路は変更せず、Write Secret欠損＋isolation unverifiedによるfail-closedを維持。非Secret承認commit変数は監査用に旧値のまま残しても現行経路を再有効化しない。

## remote backendの限界

schemaの複合primary key/platform/account/state/version>0 CHECKの存在はREAD PASS。しかし空DBでは二重INSERT拒否、競合勝者数、CASやcrash後持続性を実証できない。SQL制約の存在と実負荷の結果を混同しない。

| 契約 | reference | 実D1 |
|---|---|---|
| uniqueness / CAS | DESIGN PASS、guarded reference | UNVERIFIED |
| version monotonicity / immutable fingerprint | DESIGN PASS | UNVERIFIED。version>0は単調増加制約ではなく、fingerprint NOT NULLは不変制約ではない |
| concurrent claim | DESIGN PASS | UNVERIFIED |
| stale owner / fencing | DESIGN PASS | UNVERIFIED。現test_jobsにはowner_epoch/fencing_token列がなくfull contract未実装 |
| checkpoint durability / restart/recovery | DESIGN PASS | UNVERIFIED。現test_jobsはgeneration/metrics/improvement checkpoint storeではない |
| duplicate callback / replay | DESIGN PASS | UNVERIFIED。nonce replay ledgerとepoch/version callbackのfull remote実装は未実証 |
| ambiguous side effect / unknownから自動再送禁止 | DESIGN PASS | UNVERIFIED。今回migrationの再送0回は証拠になるが、全live dispatchの証明ではない |

schema migration成功をbackend_completeやatomicity PASSへ昇格しない。

## Worker存在と権限

公式GET /accounts/{account}/workers/scriptsは最新照会で200、対象名を返さなかった。監査JSONのABSENT_IN_CONFIRMED_LISTは「返却リスト内に対象なし」の意味。TokenのAccount-wide Worker可視性は証明できず、Account内不存在として扱わない。過去settings 403も不存在証拠ではない。GitHub全Actions historyは今回前30件を確認し、Worker作成/deploy成功の証拠は見つからない。履歴にないDashboard作成の不存在は証明できない。

公式ListとSearchの双方でWorkers Tail Read/Workers Scripts Read/Write等が必要。D1 Readだけで必ず全Workerを見られる別公式経路は確認できない。403を避けるための認証fallback・権限拡張・連続endpoint probingはしない。

2026-09-15公式authorizationではIndividual Worker Editorは既存Worker更新/deploy可、作成/削除不可。新規作成はWorkers product Admin。既存WorkerのD1 binding設定に追加D1 credentialは不要だが、bindingを付けたWorkerコードには実DBアクセス能力があるためEditorを安全なread-onlyと扱わない。

**次の本人操作は1つ：固定AccountのWorkers & Pages一覧でplm-serverless-sandbox-controlの存在を確認する。** 対象名がある/ないの結果だけ返す。今回は作成・Token作成・deployを依頼しない。これにより無駄なAdmin発行を避け、存在なら限定Editor準備、不存在なら本人bootstrap作成という次のgateを選ぶ。

## stopped deployの準備（未実行）

serverless/stopped-deploy-plan.jsonにexact Worker/Account/D1 binding、4flags trueを固定。entrypointはbootstrap-placeholder.mjs。全requestを503 disabledで返し、DB/envを参照せず、外部HTTPなし。custom domain/routes/Cron/Queue/Secret/outbound endpointなし、workers.dev/preview無効の設計。deploy/create permitted=false。

存在が確認された後にのみ、account-owned Individual Worker Editor、固定Account/固定Worker 1件、D1 Write/Admin/Billing/Token管理なしの専用短期Tokenを本人が作成する設計。予定名plm-sandbox-worker-stopped-deploy-once、GitHub Secret PLM_CF_WORKER_API_TOKEN。TTLはDashboard最短選択を本人確認、成功/失敗/timeout/unknown直後にCloudflare失効確認→GitHub Secret削除。実Token作成も今回未依頼。deployは別明示承認が必要。

STOP：不存在・scope/resource不明・他Workerへの到達・安全flag不一致・課金条件変化・bindings/route/cron/queue/Secret不明・401/403/429/timeout/unknown。未知の既存Workerなら先にread-only code/settings/active deploymentを保存し、過去versionへのrollback可否を確認する。いずれもunknown deploy自動再送禁止。placeholder作成前の状態が不存在ならrollback=停止保持＋本人判断による削除で、勝手に削除しない。

## read-onlyで完了しない実地gate

remote atomicity・full durable adapter・fencing/replay/checkpoint、Worker存在/限定権限/実deploy、test-only Secret、TEST_ONLY往復、実AI quota・実AI、実render、YouTube OAuth/private投稿、1h/24h/Improvement実地確認は未完了。reference成功と実地PASSを別欄で保つ。

Free/$0は本人Dashboard evidence PASS、API側plan値はUNVERIFIEDのまま。GitHub artifact実使用量とAI project quotaを今回確認済みとは書かない。実地の未知条件を含むため進捗95%維持（今回+0pt）。実作業時間6～12時間は暫定で、full remote adapterのschema設計により増える可能性があり、本人操作/OAuth/24h観測等の外部待ちは別。

## 公式照合資料

- https://developers.cloudflare.com/workers/authorization/ (Sep 15, 2026)
- https://developers.cloudflare.com/changelog/post/2026-09-15-granular-worker-permissions/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/list/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/search/
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://developers.cloudflare.com/d1/reference/time-travel/

Time Travel bookmark取得はPASS。復元そのもの、復元Write権限、free retention内の将来復元成功はUNVERIFIED。schema試験のため自動復元しない。
