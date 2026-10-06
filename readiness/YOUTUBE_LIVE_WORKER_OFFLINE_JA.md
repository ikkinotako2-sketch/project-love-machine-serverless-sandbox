# YouTube Worker offline successor

既存production約98%、成功run 36153932146を維持。本準備は新serverless live E2E 0/1とは別。旧pre-execution planとconsumed証拠は不変。

独立 `serverless/youtube-live/worker.mjs` にD1 Sessions/固定SQL、Queue checkpoint enqueue、owner/epoch/fence claim、dispatch durable reservation、process-local one-send capability、HMAC-SHA256 canonical v2 callback、時刻skew、crypto.subtle.verify、厳密run/script/media/intent binding、replay拒否、atomic result保存とCOMPLETE、bounded offline triggerを実装。dispatch transportはmock専用。fixture keyはtest内のみ。

実SQLiteで0008/0009のtriggerを実行。callback INSERT→UPLOAD effect CONFIRMED→job SUCCEEDED→result INSERT→outbox CONFIRMED→Queue COMPLETEの6 row mutationを確認。2番目のINSERT失敗では全体rollback。enqueue1、claim1、reservation2、send consumption1、callback6、合計11 logical row mutations/job。timeout/non204のUNKNOWN経路はenqueueを含め7。ここには生成/render/upload checkpointの準備writeを含まない。D1 index/meta/DDLのphysical rows written上限は未実証なので数値を捏造しない。

bundleは外部import不要の単一ESM sourceとbyte-identical。stopped configはworkers_dev=false、preview_urls=false、routes=[]、cron=[]、consumer無し、全4 flags=true。deploy entrypointは503固定、scheduled/queue拒否。offline ingressとtriggerは明示依存注入でのみ呼べる。deployしても自動運転しない。

BLOCKED: current quotas/secret/Worker route状態、physical DDL/index write上限、durable stage checkpoint adapter、productionのv2 callback senderが未完成。固定production refはcallback送信機能を持たない。render_run_idはrender子workflowのIDであり、pipeline run IDとのmappingを別途固定する必要がある。今は同一を推測せず不一致を拒否する。durable scriptのdispatch_inputs mappingも既存formatに対する明示adapterが必要。

新post-readonly planにparent、source/bundle/SQL/workflow hashes、論理budget、未知gateを保存。実deployment runner/HTTP envelopeとphysical write上限は未固定なのでdeploy承認を求めない。0008→postcheck→STOP→別承認→0009→postcheck。partial/unknown再applyは禁止。

今回D1 write/migration/Worker deploy/route/cron/consumer/production dispatch/upload/SNS/secret取得/004H rerun/37409541462 rerunは全0。人間操作なしでoffline CIのみ検証。
