# Generalized behavior final read-only preflight

本人によるBehavior Token登録は、33-step remote behavior testの実行承認ではない。sandbox branchのみ。固定plan raw SHA256 `452fd980ba62164f71cfe3841ea7d399ef988c6e259945d5c67487a44eaf52c7`、33 steps / mutation sends最大33 / successful logical changes最大18 / runner1を変更しない。

## Credential経路

`serverless/generalized-behavior-final-preflight.mjs` の専用transportは、Behavior Tokenを `GET /accounts/{sandbox_account}/tokens/verify` に最大1回だけ送る。送信直前に使用枠を消費するため、timeout/unknown/errorでも再送しない。redirect:error、bodyなし、Authorizationのみ。D1 /query、/import、metadata、inventory、bookmark、user verify、別endpoint、余分なheader、2回目verifyを送信前に拒否する。

Cloudflare公式endpointの `status=active` と `expires_on` の未来の有限日時を必須とする。not_beforeが存在する場合は有効な過去日時を確認する。verifyでは権限scopeを証明できないため `token_scope_api_verified=false` を明記し、token id/raw bodyは保存しない。
公式資料: https://developers.cloudflare.com/api/resources/accounts/subresources/tokens/methods/verify/

D1監査には `PLM_CF_D1_READ_TOKEN` だけを使う。auditorへ渡す環境からBehavior Tokenを除外する。Read/Behavior/GitHub history credentialは同一値を禁止。閉じたread-only SQL/GET allowlist、exact空params、Content-Type application/jsonのみ。GitHub history/branch headのGETはGitHub readonly tokenのみの別固定経路。実mutation runnerは追加しない。

## Gate

- 固定SQL/plan/before/after 4 SHA、migration FULL_APPLIED成功receipt raw SHA、behavior plan raw SHA exact。
- 全SQL/params・全before/after rows・期待changes・final rowsの固定planを保持。1 job / 1 script / 1 render / generation-render-upload effect各1 / callback1。
- `plm_rt_v1_` 5 tables / 11 triggers / 14 autoindexes exact、column counts10/13/13/11/14、全5 tables全row0（behavior identity 0を含む）。
- 既存stage2成功3 row / atomicity成功row / test_jobs0 / 全既存schema・indexes不変。_cf_KVはschemaのみ必須、content=NOT_APPLICABLE_RESERVED_UNQUERYABLE。
- inventory exact、DB size196608 bytes、fresh Time Travel bookmark。
- GitHub全workflow history、prior behavior executionなし、current final preflight run unique。過去prepare read-only preflightの成功は実testに分類しない。
- fixed prepare commit pin / event before / exact activation message / attempt1 / branch head一致。新final preflight workflowの過去実行はskippedだけ。保存済みfinal preflight receiptがあれば再試行停止。
- 実test workflow hard-disabled / allow=false / execution_approved=false / UNAPPROVED。read-only final workflowも単回実行後hard-disableしread-backする。

通常Cloudflare HTTPはBehavior verify1＋Read Token監査34＝35回（inventoryが1pageの場合）。Behavior TokenはD1 APIに0回。D1 mutation/write=0。Worker / AI / render実行 / YouTube / SNS / external provider=0。DELETE / DROP / reset / retry / resend / fallback / automatic rollback=0。

unexpected/timeout/unknownはSTOP、次requestやfallbackを送らない。diagnosticsはerrors[].codeと安全な固定bounded messageだけ。Token / signed URL / raw headers / raw provider body / untrusted exception messageを保存しない。

offline CIはkernel guard付きで全PASS必須。production / sandbox main / n8n / V1 / 既存YouTube Pipeline / PR #15/#16を変更しない。live_ready=false / posting_permitted=false / 4安全フラグtrue。

全PASS後も実testは未実行で停止し、本人へ「固定33-step generalized backend remote behavior testを1回だけ実行してよいか」と別の最終承認を求める。
