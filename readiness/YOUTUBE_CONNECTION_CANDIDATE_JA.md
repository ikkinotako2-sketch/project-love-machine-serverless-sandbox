# Connection candidate — offline complete / remote and approval gates only

既存YouTube約98%、production E2E `36153932146`を維持。新serverless live E2Eは0/1。production本体、旧plan、旧parked Worker、0008/0009、consumed markerは変更しない。

## Production candidate

base production SHAは`b0c7f429a1f58726c4a75f4fb090928cf567b585`。`production-candidate/production.patch`は次の3ファイルだけを変更する。
- `.github/workflows/youtube-pipeline.yml`: optional serverless_context、render前のrun bind、upload前のrender checkpoint、結果保存後のsigned callback。
- `.github/workflows/youtube-adapter.yml`: serverless_guardの場合SocialHub max_attempts=1、upload stream loop=1。legacy pathは既存設定を保持。UNKNOWNから新uploadやfile resumeをしない。
- `plm/entrypoints/yt_serverless_candidate.py`: canonical JSON/HMAC、独立checkpoint keyとresult key、one-send sentinel、socket timeoutとclose、処理完了statusの最大1 GET、fixed error codeのみ。

candidateは既存workflow_callを維持。pipelineとrenderのgithub.run_idは同一caller runに所属し、別workflow_dispatchのrun IDを推測しない。署名済みrun bindはrenderより前、media SHA/QG checkpointはuploadより前に保存する。metadata callbackだけでrender rowを作成しない。

現行upload artifactはqueuedで成功した歴史的証拠。この事実は不変。新callbackはowner-authenticated videos.getのuploadStatus=processed、processingStatus=succeeded、privacy=privateが全て必要。processingのままならSTOP、再upload/無制限pollはしない。

## Offline adapters

V2 generation checkpointのtitle/hook/narration/scenes/bgmをexact production inputへmap。speaker=1、captionsはscene start/end/captionから作成。output=mp4/1080/1920/30。description空、tags=game,shortsは監査済み既存V2 defaults。audience/disclosureはtrusted explicit policy。private/notify=false/scheduled空を強制。secret selectorは既存NAMEのみ。dispatch JSONはtyped booleans、event JSONのboolean stringsをsender側で復元してexact payload SHAを照合。

D1 run binding schemaは新0010候補。既存0008のjob/script/render/effect/callbackと0009 Queue/outbox/resultはそのまま使用。run bindの3 statements、render checkpointの4 statementsを各batchでcommit。SQL失敗は再試行しない。callback insertとresult insertは同一batch、trigger適用後のQueue COMPLETE/outbox CONFIRMED/job SUCCEEDEDをtestでreadback。途中failureでは全体rollback。

Cloud Queue候補はbatch最大1、重複messageはdurable stateから判断。HTTP 204をupload success/ACK扱いせず、COMPLETEのみACK可能。UNKNOWN/consumed reservationからsendしない。

dispatch transportは注入fetchのみ。durable reservationとsend consumptionを先にcommit。AbortControllerをtimeout時にabortし、redirect禁止、late 204でもUNKNOWNを維持。abortは既にサーバーへ到達した送信を取り消す保証ではないのでUNKNOWNから永久再送禁止。

## Write accounting

A: completed generation checkpoint以降は18 logical row mutations/job。generation job作成からは24。checkpoint/callbackにはtrigger row mutationsを含む。
B: completed generation checkpoint以降は14 write SQL statements/job、生成metadataの6 statementsを含め20。最大batch=4、dispatch send=1。full lifecycle successはSQLiteの実changesで検証。
C: Cloudflare billing rows writtenはREMOTE_VERIFICATION_REQUIRED。
D: DDL/index/metaの内部physical accountingはREMOTE_VERIFICATION_REQUIRED。statement数やSQLite changesをC/Dの上限として扱わない。新0010はCREATE TABLE1/CREATE TRIGGER3というstatement数のみ固定。

## Remaining gates

REMOTE: account Free/quota、artifact残量、現在Worker/source/routes/cron/consumer、protected rows、D1 transaction live behavior、billing/physical accounting。直接read connector無し。新read-only planは未承認・未起動、旧identityは不使用。
SECRET: 独立checkpoint key、callback key、repo-scoped dispatch credential、OAuth current readiness。値取得/新credential要求無し。
APPROVAL: 3-file production patch、future immutable successor production SHAの固定、0008→postcheck→STOP→別承認0009→postcheck→別承認0010、Worker deploy。base production SHAは旧成功版との比較基準でありcandidate実装を含むSHAと偽らない。approved successor commit後の新planでdispatch refをそのexact SHAに固定する。mutable main fallback無し。
LIVE: immutable refのdispatch受付、private一本、processed status、result callback→COMPLETEのlive E2E、24時間観測。新runtime硬化と004Hの未知APT診断は既存98%と独立、今回はruntime0。

すべての候補bundleはfetch503、cron/queue拒否。routes=[]、crons=[]、consumer無し、全4 flags=true。実route/trigger/upload開始は独立承認が必要。今回remote HTTP/write/deploy/dispatch/upload/SNS/secret値取得/paid操作は0。

Source evidence: https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows
Processing contract: https://developers.google.com/youtube/v3/docs/videos
