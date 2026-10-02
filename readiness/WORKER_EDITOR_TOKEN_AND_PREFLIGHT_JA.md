# Individual Worker Editor登録と停止deploy直前までの手順

現在の基準は約96%、live_ready=false、posting_permitted=false、4安全flags true。公開面は本人Dashboardの証拠としてProduction workers.dev/Preview Disabled、Custom Domain/Routes 0、Worker存在確認をOWNER CONFIRMEDとして記録。Work/API read-backではない。Version URL個別state、remote ID/codeSHA/vars/Secret/compatibility/observabilityはUNVERIFIED。以前の本人D1 binding 0は最新snapshotとして使わない。

Cloud Browserは再試行しない。スクリーンショットの現物をこのturnに取得/再読していないため「Workがスクリーンショット検証済み」とは書かず、本人の明示報告を証拠とする。以前のread-only D1 run 37064849312は当時のschema/0行証拠で、現在状態の再取得ではない。migration run 37063527954は成功1回/再送0、承認消費済み。再migration禁止。

## 次に本人が行う1操作：限定Tokenの作成と保護登録

Cloudflare fixed Account 6c8ccd6aface937ab5dabef61cb64534のManage Account > Account API TokensでCreate Token。名前plm-sandbox-worker-stopped-deploy-once。permission policyのscopeをIndividual/Specified Workersとし、既存plm-serverless-sandbox-controlだけ選ぶ。Role Editor。

Account全体Workers product Editor/Admin、他Worker、D1 Write、Billing、Token管理、DNS/Zone Routes、migration権限を追加しない。scopeの表示文言はUIで多少変わり得る。対象Workerを指定できない/余分な権限が必要と表示された場合は作成せずSTOP。単に従来のWorkers Scripts WriteをAccount全体へ付ける設定で代用しない。

TTLは保護画面で選択可能な最短期限。正確なUI最短時間は未検証なので「15分」等と捏造しない。期限が短すぎてsnapshot→本人最終承認まで間に合わない場合、Token延長/更新を自動で行わず停止し、本人判断。無期限を最短と扱わない。

作成確認画面でfixed Account/Worker1件/Editorだけ/有限期限を本人確認し、sandbox repository ikkinotako2-sketch/project-love-machine-serverless-sandboxのSettings > Secrets and variables > ActionsのRepository Secret PLM_CF_WORKER_API_TOKENへ登録。Token値はCloudflareからGitHub保護欄へ本人が直接入力する。chat/log/commit/Variableへ貼らない。本人は値でなくscope・期限・登録完了のみを報告する。

Token作成・登録はdeploy承認ではない。Secret登録だけではworkflowを開始しない。Scope/他Worker排除はAPIのexact Worker GET成功だけで証明できないため、確認画面owner evidenceとtoken_scope_api_verified=falseを併記する。

## 登録後のWork自律preflight

準備済みworkflow PLM Worker Editor Read Only Preflightはsandbox branch pushだけ、run_attempt=1、exact future commit pin PLM_WORKER_PREFLIGHT_APPROVED_COMMITが必要。現在そのpinを有効化していない。本人登録後にWorkがread-only用commitを準備し、非Secret pinをそのSHAへ合わせて1回だけ起動する。mainへmergeせず、migration経路やproductionへdispatchしない。新たなruntime SecretはEditorだけ使用し、D1 credentialをこのworkflowへ渡さない。

順番はaccount-owned verify→settings→active deployments→active version metadata→subdomain→schedules→Secret names→code content（メモリhashのみ）→active deployments read-back。全てfixed Account/WorkerのGET。1 authと8 Worker GETの計9回を基準にし、別endpoint fallback/自動retryなし。dynamic pathは取得したUUIDのversion endpointのみ。Worker呼び出し、DB query、POST/PATCH/PUT/DELETE、deploy、wranglerは一切ない。

active/有限expiryを確認。deploymentsは最新deploymentのversionが1つで割合100%を必須にし、split versionは手動照合。start/endのdeployment/version一致を検査し、取得中の変更を拒否する。version.metadata.resourcesからbindingsとcompatibilityを取得し、Worker settingsからobservability metadataを取得する。settingsとversion APIが別である点を公式資料と照合。

snapshotはexact Account/Worker、deployment/version UUID、codeSHA/etag、binding名/type、4安全varsの値だけ、Secret namesだけ、workers.dev/preview false、Cron件数、handler一覧、compatibility date、sanitized observability counts、取得時刻を残す。unknown plain_text値、Secret値、raw provider response、Token ID、raw sourceを保存しない。ソースmultipartは1モジュール以外を拒否。現コードSHA不一致なら自動修正せずSTOP。

Routes/Custom Domainsのzone-level APIやaccount全Workerの列挙で権限を広げない。今回のNONEはowner evidenceとして保持。subdomain falseはAPIで別確認する。Queue external consumerの全inventoryは限定Editorのみで実証できると仮定せずUNVERIFIED。現在code=固定fetchだけ、queue bindingなしを確認し、full consumer topologyをPASSにはしない。

403/404/429/timeout/unknown、inactive/expiry不明、snapshot欄不明、public true、binding/Secret/Cron存在、code hash不一致、deployment変化ならdeploy禁止。限られたread-only応答形が公式/実環境と不一致でも不正データをPASSに合わせて修正せず、sanitized証拠で原因確認する。

sanitized snapshotとrollback receiptを取得run ID/approved commit/config/code SHAへ紐付け、sandbox監査記録へ保存。offline CIを再検証。scope owner evidence確認も合わせ、**本人の最終deploy承認直前で停止**する。snapshotだけで自動deployはしない。

## deploy前validator

wrangler.stopped.jsonはexact name/account/DB name/id/binding、main=bootstrap-placeholder.mjs、4vars true、workers_dev/preview_urls false、routes/cron/queues空、追加env/build/service/Secret等なし。configそのもののcanonical SHA cefa60606ca3e3820116a56671d83125ea86ac6e3a5e771761dd2e3508c96cf5を固定し、比較元ファイルだけを差し替える改変も拒否。

code SHA 6c5d726f96d56dac792ff739f87227926197891f1149b1dedeeac38e67128451を固定。DBアクセス、fetch、SNS/YouTube/GitHub/AI等の追加コードはhash不一致で全て拒否。policyはservice_bindingsを含む全禁止配列の空を要求。worker handler runtimeも503 disabled、DB/envアクセス0、fetch0をguarded CIで確認。D1 binding設定候補はあるがこのturnにremote bindingを追加しない。

## rollback（現在IDはnull）

IDを推測しない。actual read-only snapshot前はrollbackReadiness=BLOCKED。旧固定停止code、binding/Secret/Cronなし、fetch handlerだけ、public false、stable deployment read-backを必要にする。snapshot IDはUUID形式、owner evidenceだけでは代替しない。

rollback receiptは旧deployment/versionと公開状態/vars/bindings/compatibility/obsのsnapshotを保持。deployment rollbackと非version設定の復元は別であり、一方の成功から他方も戻ったとは推測しない。旧stateへのrollbackでpublic routeを再有効化しない。D1 binding removal等の設定戻しは別承認が必要で自動削除しない。remote bindingを戻してもDB内容を変更/復元しない。

## 将来の1回deploy（設計のみ）

本人最終承認はexact Account/Worker/DB/config/code SHAとdeployment base IDへ束縛する。GitHub exact branch/head/first attempt/unique run historyとreceiptを最終照合。send前にATTEMPT_CONSUMEDを監査ログへ記録し、1回のみ送信する。unknown/timeoutやclient restartで承認を再利用しない。rerun/新run/別commitで再upload/redeployを自動実行しない。

成功応答後もWorker/settings/version/deployment/subdomainをread-backし、DB exact binding、4vars true、workers.dev/preview false、停止code固定SHA、no Secret/service/queue/Cron、公開Routeなしを確認。route owner evidenceとAPI値は区別し、確認不足はPOSTCHECK_UNVERIFIEDでmanual reconciliation。worker本体へHTTPテストrequestは送らない。全request503はcode検証により維持する。

成功/失敗/timeout/unknownの直後は、本人がCloudflare Editor Tokenを失効→失効確認→GitHub PLM_CF_WORKER_API_TOKEN削除。Workは失効済みと推測しない。preflight段階で中断したTokenも放置せず本人失効が必要。実deploy最終承認待ちの間は期限付きで保護し、expireしたらdeploy STOP。Token管理API権限を追加して自動失効する設計にしない。

Worker binding配置はremote atomicity/CAS/concurrent claim/fencing/generation checkpoint/callback replay ledgerのPASSではない。現test_jobsはfull durable schemaではない。次のTEST_ONLY往復、AI、render、OAuth/private投稿、1h/24h/Improvementには別gate/別本人承認が必要。100+ accountsは別BLOCKER。

## 公式再照合（2026-10-03）

- https://developers.cloudflare.com/workers/authorization/
- https://developers.cloudflare.com/changelog/post/2026-09-15-granular-worker-permissions/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/settings/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/methods/list/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/subdomain/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/content/methods/get/

Individual Worker Editorは既存Worker deploy可、作成/削除不可。binding追加に別D1 Write API credential不要だが、bindingされたコードはDB操作能力を持つ。停止code固定の別gateを維持する。
