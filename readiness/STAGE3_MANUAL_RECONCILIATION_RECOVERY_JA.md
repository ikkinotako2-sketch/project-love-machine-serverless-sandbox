# Stage3 manual reconciliation / 新規explicit-batch候補

## 結果

read-only run 37109169905 / attempt 1 は NOT_APPLIED / PASS。
旧送信 run 37108371746 の HTTP 400 / UNKNOWN / SENT receipt は変更せず保持する。
現在のremote適用状態を別receiptで解決したもので、旧HTTP応答をSUCCESSに書換えない。

Account 6c8ccd6aface937ab5dabef61cb64534、DB 18050cf6-934e-4f3a-a1cd-5041bac1c35e / plm-serverless-sandbox-state。
全ページinventoryは1件、他D1=0。

|予定object|現在|
|---|---|
|durable_stage2_job|不存在|
|durable_stage2_checkpoint|不存在|
|durable_stage2_callback|不存在|
|durable_stage2_job_guard|不存在|
|durable_stage2_checkpoint_guard|不存在|
|durable_stage2_checkpoint_insert_guard|不存在|
|durable_stage2_callback_apply|不存在|
|durable_stage2_callback_immutable|不存在|
|durable_stage2_callback_insert_guard|不存在|

既存schema・columns・indexes・triggerは基準と一致。backend_probe_v1成功rowの15列はexact一致（succeeded / version 3 / contender_a）。test_jobsは11列・0行。_cf_KVはschema不変、内容の独立読取は行っていない。
DB size=40960 bytes、基準と同じ。
bookmark=00000011-00000000-000050f9-807ceddf3c18dba8e078311be8541cbc。
read-only API=10（GET 4 / SELECT・PRAGMA query POST 6）。mutation/write=0。

cleanupは本人証拠：旧stage3 Token失効/削除、GitHub Secret削除、Read Tokenのみ維持。独立失効検証・Token管理権限追加なし。

## HTTP 400原因と仕様

確定：旧形式は {sql: 複数DDLを連結した全文, params:[]}、HTTP 400、raw provider error code/bodyは保存されていない。具体的なparserエラーを遡って確定できない。
公式D1 REST queryはsemicolon連結SQLと明示的batch配列の両方を定義する。そのため複数DDLが一般に禁止という結論は誤り。
Cloudflare workers-sdk公式リポジトリ issue 15690 / 15314 にはmultiline trigger等の類似報告があるが、報告者の再現であり今回の原因確定・修正版成功保証ではない。
旧SQLはLF・uppercase BEGINで、lowercase BEGINやCRLFの問題とは一致しない。
Workers binding batchのtransaction説明をRESTのDDL原子性保証へ拡張しない。RESTの部分適用・trigger parsing・具体的failure rollbackはUNVERIFIED。

参照（2026-10-03照合）:
- https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://github.com/cloudflare/workers-sdk/issues/15690
- https://github.com/cloudflare/workers-sdk/issues/15314

## 新候補（未実行）

0004_durable_stage2_explicit_batch.sql：3 CREATE TABLE + 6 CREATE TRIGGER、top-level DDL 9。
SQL SHA256=c2d3c40447490932df83ecf52797d493787cc2a76a4a4efbc1b0a11a633381c4。
request SHA256=7a22f2ec5eed90e658f934fb6005289752470193a213b084cfb1f21700278d58。
新expected-schema SHA256=2a9d432b5820f8d2bd5b0d18e54dad41d5b03369368e0b429ab067ff9c2ffb03。

9個のcomplete statementを明示的batch要素に分離。triggerの内部semicolonを単純splitしない。
全要素single-line、quoted literalのbytesを保持。DDL意味・constraintsは元候補と同じlocal referenceで検証。
新しいrequest方式・新ファイル・新receiptとして扱い、旧SQL/SENT receiptは不変。
DROP / DELETE / ALTER / rename / 既存table変更=0。IF NOT EXISTSを再送理由に使わない。
期待schema：3tables / 6triggers / columns16・11・9 / autoindexes8 / rows0。
SQLite reference PASSはD1 API成功の証拠ではない。新方式remote成功はUNVERIFIED。

## 次回の実行条件

新専用Token案：plm-sandbox-d1-stage3-recovery-once-v2。
Secret：PLM_CF_D1_STAGE3_RECOVERY_TOKEN（旧Token・Secretの再利用禁止）。
account-owned / Account D1 Edit/Writeのみ / exact Account / finite short TTL。
Workers・Admin・Billing・Token管理・DNS・Routes禁止。
Account全D1に届くため直前inventory1件・他D1=0が必須。scopeはowner evidence。

Secret登録だけでは承認にならない。新workflowはhard-disabled・allow=false・owner=UNAPPROVED・CLI read-onlyのみ。
登録後は新exact commitでaccount-owned verifyとRead Token auditを別承認経路で準備し、実migration前に本人の最終承認を要求する。
旧runは再実行しない。旧失敗を履歴上保持し、新NOT_APPLIED receipt SHAとfresh NOT_APPLIED確認がない限り進めない。
新recovery履歴は全ページ確認、過去non-skipped recovery runがあれば拒否。SENT journalはmutation前に排他的予約し、再起動・cancel時は自動resumeしない。
現workflowにlive mutation CLIはない。将来の実行activationには履歴pagination・durable journal・exact approved pin・receipt lockを結線した専用entryと別本人承認が必要。

予算：新migration HTTP最大1回、batch要素9、retry/resend/fallback/rollback=0。
送信後はRead Tokenのみでpost/reconciliation最大1セット。HTTP成功＋期待FULL_APPLIED exact時だけSUCCESS。
400/5xx/timeout/reset/parse failure/partial/unknownは再送禁止・後続STOP。full schema確認でもACK欠損なら自動SUCCESSにしない。
部分適用なら既存objectを削除/再CREATEせず、別の追加専用案を本人判断へ戻す。
rollbackは自動なし。Time Travel bookmarkは証拠として保存し、restoreには別本人承認が必要。

migration後はToken失効とGitHub Secret削除が本人確認されるまでstage2試験へ進まない。
旧stage2 planと旧schema証拠は保持。新DDL表記に合わせたstage2 exact preflight/schema fingerprintの更新は成功schemaがremote確定した後に別準備する。

## Safety / readiness

今回Python 453 / Node 403 = 856 PASS、FAIL 0（guarded local結果、GitHub CI receiptは別保存）。
今回追加44tests（Python8 / Node36、前回812比）。
CI external_api_calls=0 / D1 write=0 / render_executions=0 / posting=0。
remote auditだけCloudflare read-only10calls。Worker deploy/invocation/AI/render/posting/livejob=0。
live_ready=false / posting_permitted=false / 4flags=true。
remote stage1固定範囲PASSは保持。stage2 fencing/checkpoint/callback/ambiguous recoveryはremoteUNVERIFIED。
100+accountsは別BLOCKER。production/main/n8n/V1/既存Pipeline/PR15/16は変更しない。
進行度の概算は98%維持（今回+0pt）。残り実作業は概算300–660分、認証待ちと1h/24h観測待ちは別。
