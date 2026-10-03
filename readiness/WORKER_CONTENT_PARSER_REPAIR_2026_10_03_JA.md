# content/v2 parserのoffline修正・公式照合

2026-10-03。旧run 37085331907（GET8回、attempt1）のfailure receiptと結果文書は変更・削除しない。本修正は後続証拠。本人が旧Editor Tokenを失効しGitHub Secret PLM_CF_WORKER_API_TOKENを削除したことはOWNER EVIDENCEとして記録し、Work/API失効確認とは呼ばない。旧active確認は過去時点の事実。

## 原因の判定

第一候補はPlayground由来multi-module multipartを旧files.length!==1条件が拒否したこと。本人画面のindex.js/data.js/welcome.htmlを模したPUBLIC SYNTHETIC PLAYGROUND-LIKE fixtureで、Node Response.formDataが3 file partを返し旧条件を拒否することを再現した。今回実provider responseを再現・取得したものではなく、runの具体的例外が記録されていないため確定原因ではない。

別候補はContent-Type mismatch（旧raw JavaScript regexは+moduleを許容していなかった）、128KiB超過、multipart framing、File/string coercion（filename無しのpartを旧file filterが落とす）、metadata/entrypoint不足、module MIME、invalid UTF8。各境界をsyntheticで検証。旧runのraw responseやsourceを再取得しない。

## 公式仕様の照合

取得日2026-10-03。authenticated Cloudflare API、D1 query、Worker HTTP invocationは0。公開Docs閲覧とGitHub公式SDKソース読取は調査用であり、CI/runtimeのexternal_api_callsとは別集計。

| 資料 | 確認したこと／限界 |
|---|---|
| GET Workers Scripts content/v2 | raw script contentの取得。Docsは単一JSON envelopeや固定Content-Typeを保証する記述を示していない。HTTP200のみでresponse shapeを決めない |
| Script uploadとcontent update | modules配列、metadata.main_moduleまたはbody_partがentrypointを参照。JS+module、plain JS、text、Wasm/binary等を扱う |
| Multipart upload metadata | metadataはJSON。bindingsにはSecret値が含まれ得るためraw metadataを監査ログへ保存しない |
| TypeScript SDK content.ts | GETはResponse、__binaryResponse=true、blob例。JSON resultを想定しない |
| Python SDK content.py | GETはBinaryAPIResponse。with_raw_response／streaming対応 |
| Go SDK scriptcontent.go | GETは*http.Response。Update側はmultipart writer、GETはraw response |
| Wrangler cfetch/internal.ts | multipart responseをformDataとして処理し、cf-entrypoint headerでentrypointを得る。string partもFile化して扱う。既定src/index.jsへのfallbackは今回採用しない |
| Versions API | resources.bindings／script.handlers／script_runtime.compatibility_dateとversion IDを扱う。contentのentrypointをversion metadataから推測しない |

公式Docs：
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/content/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/update/
- https://developers.cloudflare.com/api/typescript/resources/workers/subresources/scripts/subresources/content/methods/update/
- https://developers.cloudflare.com/workers/configuration/multipart-upload-metadata/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/methods/get/
- https://developers.cloudflare.com/api/typescript/resources/workers/subresources/scripts/subresources/content/methods/get/
- https://developers.cloudflare.com/api/python/resources/workers/subresources/scripts/subresources/content/methods/get/
- https://developers.cloudflare.com/api/go/resources/workers/subresources/scripts/subresources/content/methods/get/

公式SDKソース（GitHub connectorで実読。web retrievalのGitHub表示は失敗したため別取得で照合）：
- https://github.com/cloudflare/cloudflare-typescript/blob/main/src/resources/workers/scripts/content.ts
- https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/workers/scripts/content.py
- https://github.com/cloudflare/cloudflare-go/blob/main/workers/scriptcontent.go
- https://github.com/cloudflare/workers-sdk/blob/main/packages/wrangler/src/cfetch/internal.ts

照合時の各main SHAはJSON証拠に保存。これは閲覧時点の照合であり、過去failure responseの仕様・Content-Typeを確定するものではない。

## parser contract

総量128KiBは据置。公式upload最大量をこの監査parserへ自動採用しない。1-accountの小さい停止bootstrap確認用の保守的ローカル上限として、module最大8、各64KiB、metadata8KiB、part header2KiBに制限する。3-module fixtureはこの範囲に収まる。実bodyが超える場合はBODY_TOO_LARGE等でSTOPし、盲目的に上限を増やさない。

bounded bytesを自前の限定multipart/form-data parserへ渡す。fileの最初／最大size／Fileクラスかどうかから選ばない。metadata JSONは全object階層のduplicate key・malformed・invalid Unicodeを拒否した後にparse。main_module/body_partのいずれか1つだけを使用し、metadataが無い場合は公式Wranglerが読むcf-entrypointだけを使用する。双方あれば一致を必須にする。単一raw JS bodyだけはbodyそのものをmainとし、raw-body.jsという監査表示名がsyntheticであることを記録する。

重複metadata／part name、missing main、unknown selector、両entrypoint指定、filename不一致、unsafe名、unsupported MIME、invalid UTF8を拒否する。今回の停止Worker向けローカルpolicyはASCII flat filenameのみ、slash/backslash/percent traversal/..を拒否し、filenameがある場合はpart名との一致を要求する。正当な別module構造でも未対応なら推測で通さず停止する。

JS4種類（+module含む）をmain MIME allowlistにする。追加moduleはtext/plain、HTML、JSON/source-map、Wasm/octet-streamを限定許容。text/html/application/jsonは監査用opaque resourceとしてのローカルallowlist拡張で、Cloudflare uploadの全MIME保証を主張しない。Python等の未対応種類は停止。binaryはUTF8やJSにdecodeせずbyte hashだけを取る。mainがbinary/text/HTMLなら拒否する。MIMEの未知値やraw metadata/headersを診断に出さない。

snapshotにはmodule count、sanitized name、MIME、bytes、全module SHA、選ばれたmain名とmain SHAのみを追加。source/raw multipart/raw metadata/Secret値は保存しない。module順・unused module追加でmain SHAは不変だが、inventoryは全moduleを示す。raw main bytesの空白・改行・quote等は正規化しない。AST/semantic equivalence gateなし。

## gateの分離

snapshot_acquired／snapshot_passは全readと開始・終了deployment/version一致を満たしたsnapshotの取得を表す。main SHA mismatchでも完成snapshotを保存する。rollbackのDESIGN PASSはcomplete inventoryとstable restore target取得を示し、candidateとのコード一致を要求しない。自動rollback・rollback実行承認ではない。

deploy_readinessは別にraw main SHA一致、module1個、no unexpected binding/Secret/Cron、fetch handlerだけ、public false、owner Routes/Domains NONE、安全vars値、compatibilityを要求する。main SHA一致でもunused moduleがあれば、候補の単一停止コードと同一とは判定せずBLOCKED。実deploy許可は常にfalse。candidate SHAは変更しない。

## sanitized diagnostics

failure_code／failure_stageとcontent_type_family、bounded_total_bytes、part_count、sanitized parts{name,MIME,size}、selected mainを保存可能にした。BODY_TOO_LARGE、MODULE_TOO_LARGE、CONTENT_TYPE_UNSUPPORTED、MULTIPART_PARSE_FAILED、METADATA_MISSING/DUPLICATE/INVALID/DUPLICATE_KEY、MAIN_MODULE_MISSING/NOT_FOUND/AMBIGUOUS/TYPE_UNSUPPORTED、DUPLICATE_PART_NAME、MODULE_COUNT_LIMIT、MODULE_TYPE_UNSUPPORTED、MODULE_NAME_UNSAFE、UTF8_INVALID、HASH_FAILED等を固定codeで出す。外部例外messageやstackをそのまま保存しない。

## 検証と次段階

新規parser fixture-drivenテスト40項目＋preflight統合テスト7項目。single/raw/multipart、metadata/header、index.js/data.js/welcome.html、binary、重複、不在、不正型、サイズ超過、順序、byte SHA、old rejection再現、diagnostics privacy、SHA mismatch時snapshot保持、rollback completeness、Secret欠損0通信を含む。

ローカル全検証：Python366 PASS、Node172 PASS、合計538 PASS／FAIL0。native seccomp/socket/exec guard維持。external_api_calls=0、Cloudflare API0、D1 query0、deploy0、live job0、render0。push後offline CIの実結果は別receiptで記録する。旧approved commit pinは変更せず、新修正commitからread-only preflightを起動しない。job gateはSHA不一致でSKIPPEDとなる必要がある。

全体96%据置（+0pt）。live_ready=false、posting_permitted=false、4安全flags true。remote atomicity/CAS/fencing/concurrent claim/checkpoint/replayはUNVERIFIED。test_jobsはfull durable schemaではない。100+ accountsは別BLOCKER。

offline CIもPASSした後の次の本人1操作は、account-owned plm-sandbox-worker-stopped-deploy-once-v2をSpecified Workersのplm-serverless-sandbox-control 1件だけ、Individual Workers Editorのみ、有限TTLで作成し、sandbox GitHub Secret PLM_CF_WORKER_API_TOKENへ保護登録。Admin/他Worker/D1Write/DNS/Routes/Billing/Token管理は付けない。Token値はchat/log/commitに表示しない。

登録は再preflight承認ではない。新runを実行する別承認後に新exact SHA pinを設定し、attempt1・GET only・fallbackなし・retryなしの1回だけとする。旧run rerun／失効Token再利用／deploy自動実行は禁止。remote snapshotが完成してもdeployは別承認。中断またはdeploy完了時の本人Token失効・GitHub Secret削除手順を維持する。

残り実作業は概算360〜720分。1h/24h観測の最低24時間待ちと本人操作待ちは別。production/sandbox main/n8n/V1/既存Pipeline/1h/24h/Improvement/PR15/16/migration historyを変更しない。
