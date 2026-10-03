# Canonical stopped Worker 置換準備

方針承認のみ。実deploy未承認・未実行。rollback baseはrun 37088180262のstable snapshotを固定SHA receiptで保持する。取得後のremote driftは未確認であり、承認後、PUT直前に9 GETで全sanitized baseを再比較する。

実行候補は停止placeholder 1module、exact DB bindingと4flags=true。既存3module・SHA不一致・varsなしを受け入れた置換方針であり、旧remoteコードをcandidateと同一として扱わない。compatibility dateは旧2026-10-02から固定candidateの2026-10-01へ置換する。公開面falseはpre/post GETで必須、設定変更APIは使わない。

公式Script Upload APIのPUT 1回はversionとdeploymentを暗黙作成する。Wrangler/SDK retryを使わず、固定metadata + exact placeholder bytesのmultipartを直接1回送る。metadataはmain_module、exact D1 id、4plain-text vars、compatibility date、keep_bindings=[]、keep_assets=false、logpush=false、tail_consumers=[]。routes/cron/queues/secrets等の追加APIは使わない。

実行workflowは将来のreadiness/STOPPED_DEPLOY_EXECUTION_AUTHORIZATION.json追加pushだけが対象。現在このファイルは存在せず、allow/pin/approval変数も今回設定しない。本人deploy承認後にだけ、承認file、exact activation commit、allow/pinを準備して1回実行する。run_attempt=2拒否、全ページのGitHub run historyで以前の非skipped runを拒否、concurrency、PUT前のexclusive intentを使用する。これはCloudflare側のatomic CAS/Exactly Once証明ではない。

PUT後は応答にかかわらずGET-only post-readbackを1回試みる（最大8 GET）。成功応答とpostcheckが共にPASSの場合のみ成功。timeout/5xx/unknownはreadbackが一致してもmanual reconciliation。PUT再送0、自動rollback0。結果後は本人にToken即失効とGitHub Secret削除を求める。

rollbackは別本人承認。保持された旧versionの存在を再GET確認してから旧versionへのdeploymentを検討する。raw sourceは保存しないため、Cloudflare側version retentionが必要。現時点のrollback DESIGN PASSはbaseが特定されていることを意味し、実restore可能性はUNVERIFIED。旧varsなし・旧3moduleへ戻ることも明示して承認を取る。

Routes/Custom Domainsはowner evidenceを維持。remote 503は呼び出さずfixed SHA + offline実行で検証する。D1 DB名はconfig由来で、remote bindingはID照合のみ。Queue外部consumer inventoryは権限なしでUNVERIFIED。remote atomicity/CAS/fencing/checkpoint/replay、AI/render/publishはこのdeployでPASSにしない。

今回実Cloudflare API=0、mutation=0、deploy=0、DB query=0、live job=0、render=0。
