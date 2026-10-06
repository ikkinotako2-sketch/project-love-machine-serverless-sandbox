# 既存98%と新serverless経路の残作業

## A. 既存production YouTube自動化：約98%

これはユーザーのプロジェクト進捗基準であり、工数を計測した割合ではない。
run 36153932146（attempt 1、head 2fa012dd4f9630bf414533e4977b8390952a6794）はinitialize、VOICEVOX、FFmpeg、render、Quality Gate、YouTube Adapter/upload、pipeline result保存がSUCCESS。
artifact 10872563241のZIP digestはGitHub metadataと一致し、JSONはstatus=succeeded、video_idあり、voice/render/quality_gate=succeeded。
現在main b0c7f429a1f58726c4a75f4fb090928cf567b585との全tree比較で変更はdocs/COMMAND_CENTER.mdのみ。主要4ファイルを含む実装コードは同一。
過去のupload受付時点のyoutube_status=queuedはAPI受付後の処理待ち。既存E2E成功の証拠を取り消さない。処理完了や当時の公開範囲を追加で推測しない。

現時点で既存本体の新たな故障は実証されていない。004HのBLOCKEDをAの未完成の根拠にしない。
OAuthはHISTORICALLY_CONFIRMED / CURRENTLY_UNVERIFIED。現在存在しないと判定せず、値を取得しない。
既存Adapter workflowにもconcurrencyとupload前のcross-run claim artifactがあり、成功runで保存されている。30日retentionなので恒久ledgerとは分ける。

## 残り2%の具体的受入作業

「1つのYouTubeアカウントで、既存pipelineを継続運転する」という範囲で固定する。100+アカウントやSNS拡張は今回の2%に含めない。

1. テーマQueueから固定台本checkpointを取得し、1jobのdispatch予約までをクラウド側で接続する。manual dispatchを運用前提から外す。未知結果はSTOPし、同jobを再送しない。
2. 既存pipeline resultを認証済みcallbackとして受け取り、job/account/epoch/fence/script/mediaを照合して永続保存する。結果保存とQueue COMPLETEを同じtransactionで確定し、次jobのeligibilityを開く。error/unknownはDoneにしない。
3. $0のcurrent runner/storage/provider条件と現在のOAuth readinessを、値の非表示を維持して確認する。past successはcurrent readinessの代替にはしない。n8nの現行稼働/無料条件やAI生成の現行entitlementは今回のGitHub証拠から確定できない。
4. 明示承認された1本のprivate確認と、bounded triggerを使う24時間の無人運転を受入確認する。QG PASS、新規claim、notify=false、1本を確認して実upload前でSTOPする。public/unlisted/SNSは許可しない。

1〜2のSQL/契約/referenceは今回offlineで進めた。実接続・deploy・運転開始は実施しない。
目安は承認後のAの配線/受入に60〜120分の能動作業、無人観測は1,440分。承認待ち・current認証/無料容量問題・CのAPT原因特定は含められず、全体の完了時刻は未確定。

## B. serverless移行：offline Queue/claim/result候補PASS、live E2E 0/1

既存0008 provider-neutral schemaをbyte-exactに再利用し、0009 proposalで3つの新tableと10 triggerを追加する。
0008自体も未承認candidateであり、deployed v1 schemaの証明をv2/v1 Queueへ流用しない。
旧schema/table/markerは変更しない。実Cloudflare application/deployは0。

SQLiteQueueCandidateはgeneration checkpoint COMPLETED/CONFIRMED後だけQueue登録を許す。owner/epoch/fence/versionでclaim、dispatch予約を送信前にcommit、send_attemptsは最大1。予約したinstanceだけが1回のfake send capabilityを持ち、接続再開後はRESERVEDでもresume不可。timeout/non-204はUNKNOWNで永久停止する。
結果は既存0008のrender QG/媒体digest/callback/result_idと照合し、private/processed/notify=falseの固定projectionのみ保存する。result/outbox/Queue COMPLETEをtriggerで原子的に更新する。結果保存前やUNKNOWN時に次jobを開かない。
新候補のprocessed条件は、過去の既存pipeline成功条件より厳格な独立gateである。

Disk SQLiteのconnection-close/reopenと2接続の同時claimをテストする。別processの起動、power-loss耐久性、D1/多regionでの実証ではない。
Queueのlifetime capは32。tombstoneを消さずcapでSTOPするため、無期限運用の容量証明ではない。無料枠や敵対的ingressに対する支出保証にも使わない。
dispatch proposalはplan用のdataであり、実workflow_dispatch requestではない。production workflowは安全フラグを受け取るwrapperではないので、proposalを直接送信しない。transport、callback署名verification、実D1 adapter、cron/queue consumerはlive接続していない。

今後の境界はfresh remote schema/quota read-only preflight、exact migration/query/workflow hashes、独立one-shotの承認である。今回はcredential付workflowもruntime markerも作らない。

## C. runtime reproducibility / hardening：新経路のみBLOCKED

004H run 37403151934は永久consumed。ffmpeg simulation 1回 rc100、remaining 0、unknown GlobalError E fingerprintでsafe stop。
004IのNO_EXACT_MATCH_IN_FROZEN_SOURCE_CONFIRMED_GLOBALERROR_E_TEMPLATESを維持する。root cause/transaction proof/install authorizationを推測しない。
root10、APT source pockets/config/solver、frozen source fixtures/evidence、既存marker/runtime workflowは不変。004H retry/rerun/resumeは0。
固定Python・immutable VOICEVOX・speaker・FFmpeg/fontの新経路の実証は未完。既存成功コードを捨てて作り直す理由にはしない。

## D. 完全放置運転：接続と受入が未実施

n8nのproducer/result consumerとの既存入力互換性は維持する。Queue/claim/resultをserverlessへ移す境界を準備したが、triggerは無効のまま。
24時間観測、current $0 provider entitlement、quota/retention、unknown停止通知をliveで受入確認していない。無料契約を追加したりpaid runnerを有効にしない。

今回の全安全フラグはtrue。YouTube upload/004H rerun/production変更/Cloudflare write-deploy/secret値取得は全て0。
