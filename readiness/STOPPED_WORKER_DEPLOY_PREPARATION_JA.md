# 停止Workerの公開URL無効化・限定Token・deploy候補

2026-10-03本人報告：fixed Accountのplm-serverless-sandbox-controlを作成し停止placeholderをdeploy済み。503 disabled、D1 binding 0、workers.dev route有効、job/render 0、4flags true。本人の作成/deployはowner evidenceでありWorkの新deployとして数えない。累計deployは少なくとも本人の1回を含むが正確な回数/IDは未取得。

## Cloud Browser再試行

WorkのCloud Browserからfixed AccountのWorkers & Pagesへアクセス。Cloudflareのセキュリティ検証と「私はロボットではありません」表示。1回reload後も継続。CAPTCHA操作0回、迂回・別経路probeなし。worker設定に到達していないためworkers.dev無効化0回、settings snapshot/version/deployment/metrics取得未実行。

本人ブラウザの正常セッションはCloud Browserに共有されない。次の本人操作はWork Cloud Browserのセキュリティ検証だけ。Token作成や本人ブラウザでの再ログインを同時に依頼しない。検証がこのCloud Browserで通らない場合、同一siteを無制限reloadせず代替経路を別途判断する。

## その後のread-only snapshotと公開URL変更

対象Account 6c8ccd6aface937ab5dabef61cb64534、exact Worker plm-serverless-sandbox-control。

1. Worker detailsからactive deployment ID・全active version ID/割合・停止コード・bindings/vars/Secret有無・Cron/Queue/routes/custom-domain/subdomain/version URL・requestsの期間/件数を記録。Secret値は表示/保存しない。account-wide他Workerは変更しない。
2. 現在placeholderが503 disabledのみ、DB/access/outboundなしと照合。本人報告とWork観測を別欄で保つ。
3. authorized workers.dev disableを実施しread-back。Version URLsも別項目としてdisableしread-back。preview_urls省略やworkers.dev falseだけから既存Version URLs無効を推測しない。URLを開いて検査requestを増やすのではなく設定値を確認する。
4. custom domain/route/cron/queue/secretが想定外に存在した場合は保護対象や用途が不明なのでSTOP。無条件削除しない。
5. requestsを期間付きで確認。既知の手動503確認requestは0でなくても即異常扱いしない。用途不明のrequestはmanual reconciliation、healthyにはしない。

## Token最小設計（未作成・未登録）

- 名：plm-sandbox-worker-stopped-deploy-once。
- account-owned Token。Individual/Specified Worker scope、fixed Account内のexact Worker1件のみ。
- Role Editor。Account-wide Workers Editor、Workers Admin、他Worker、D1 Write、Billing、Token管理、DNS、Zone Routes権限は付与しない。
- GitHub sandbox Secret PLM_CF_WORKER_API_TOKEN。Token値はチャット・ログ・commitへ出さない。
- TTLは本人保護画面の最短設定を選ぶ。UIの正確な最短値は未確認なので分数を確定記載しない。expiryが返れば期限内を確認。expiry返却なし/無期限ならowner確認なしに進めない。
- 作成後のverifyはaccount-owned /accounts/{fixed Account}/tokens/verifyだけ。user-owned fallbackなし。active/scope/TTLはAPI確認とowner evidenceを分け、raw response・Token IDを保存しない。
- deploy成功/失敗/timeout/unknownの直後にCloudflare本人失効→失効確認→GitHub Secret削除。Tokenの失効済みをWorkが推測しない。

公式2026-09-15authorization/announcementを再照合。Individual Worker Editorは既存Workerの更新/deploy可、create/delete不可。D1 binding追加のために別D1 Write API Tokenは不要。ただしbinding後のWorkerコードにはDBを直接操作する能力があるため、限定EditorをDBへの安全性保証と扱わない。exact停止コードhash、Secretなし、no-fetch/no-DBを別gateで固定する。

DNS/Routes権限なしのまま、既存の公開状態を先に本人承認済みDashboard操作で止める。将来deployツールが不要なzone列挙等で403を返しても自動で権限を拡張しない。

## 実deploy候補config（未実行）

serverless/wrangler.stopped.jsonはWrangler用JSON。停止entrypoint bootstrap-placeholder.mjs、name/account exact、DB binding=DBとdatabase ID/name exact、4vars true、workers_dev=false、preview_urls=false、routes=[]、triggers.crons=[]、queues.consumers/producers=[]、no_bundle=true。build hook/env override/追加module/dispatchなし。

custom_domains/secrets/outbound_endpoints=[]はstopped-deploy-plan.jsonで補助policyとして固定。非対応の独自fieldsをWrangler実configへ混ぜない。空配列configを既存remote Secret/routeの不存在証拠とは扱わず、先のremote snapshotを必須とする。

停止code SHA256：6c5d726f96d56dac792ff739f87227926197891f1149b1dedeeac38e67128451。現在remote codeと同一であるかは未取得。deploy前にremote sourceと照合する。hash一致以外のコードを自動実行しない。

stopped-deploy-contract.mjsはpure validator。wrong Worker/Account/DB、workers_dev true、preview_urls true、unsafe/missing flag、route/Cron/Queue/Secret/outbound、extra config/env override、変更codeを拒否。candidateへfetch/DB accessを追加した場合はhash拒否。runtime testでRequest各methodに503、DB/env access 0、fetch 0も実証する。機械結果のdeploy_permittedは常にfalse。

## rollbackと一回送信

現deployment/version IDはnull（UNVERIFIED）。owner reportから架空IDを作らない。rollbackReadinessはremote snapshot欠損/owner evidenceだけではBLOCKED。snapshot取得後に旧停止versionをrollback候補として記録し、binding/flags/public-route設定も別snapshotに残す。rollbackで旧workers.dev有効状態を復活させない。旧code/varsが不明ならrollback候補としてPASSにしない。

実deployは次の本人最終承認後のみ。config SHA/code SHA/Account/Worker/DB/remote公開無効/限定Token/rollbackを直前照合し、1回send。timeout/unknown後に自動再deploy、再upload、同workflow rerunはしない。停止してread-only deployment/version照合→manual reconciliation。deploy後もplaceholderはDBを読まず書かず、外部fetchなし、503 disabled。D1 binding追加を今回UIで行わない。

migration承認は消費済み、今後0001再migration禁止。production/n8n/V1/既存YouTube/1h/24h/Improvement/PR15/16を変更しない。live_ready/posting_permitted=false、100+ accountsは別BLOCKER。

## 公式資料

- https://developers.cloudflare.com/workers/authorization/
- https://developers.cloudflare.com/changelog/post/2026-09-15-granular-worker-permissions/
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://developers.cloudflare.com/workers/versions-and-deployments/version-urls/
- https://developers.cloudflare.com/workers/configuration/routing/workers-dev/
