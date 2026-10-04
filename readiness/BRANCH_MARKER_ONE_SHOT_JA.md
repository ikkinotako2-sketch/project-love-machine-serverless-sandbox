# Branch marker one-shot offline candidate

この設計は旧 `ONE_SHOT_EXECUTOR_OFFLINE_JA.md` の2 blockerに対する後継です。
コード準備とowner承認とlaunchを分離する。今回markerを作らない。

## 固定境界

- repository: `ikkinotako2-sketch/project-love-machine-serverless-sandbox`
- branch: `plm-offline-readiness-v1-20261002`
- ancestor baseline: `5b16c7f826e4db29b9112cbf5849a2c51d0b3120`
- sandbox main baseline: `8ac2337a37072ae23f7781e2f47e8dfc7016b30f`
- fixture: `manual-japanese-script-fixture-v1`。3種類の既存SHAは変更しない。
- production: `25f24bc4e6a20164c5549f746fc0eefcedf5d178`。変更・実行なし。
- ユーザーPC runtimeは0。Workのクラウド作業環境ではguarded offlineテストだけ。

既存run `37205369028` のAPI readで `event=push`,
`head_branch=plm-offline-readiness-v1-20261002`, `conclusion=success` を確認。
そのrunのheadは `c87e9caf32aac403622ecd785de64848ab7c0919`。
後続receipt commitの `5b16...` とCI実行headを混同しない。
新設push triggerはbranchとmarker pathのAND条件。main登録・dispatchは不要。
公式仕様: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
GitHub tokenによるpushの再起動抑止には注意し、将来launchは今回のoffline pushと
同じowner-authorized connector経路を使う。workflow自身はpushしない。

## AUTOMATION_MONOTONIC_CONSUMPTION

primary evidenceはGit marker commit。GitHub run historyは削除可能なのでsecondary auditだけ。

1. ownerがCI全PASSのexact preparation headを承認する。
2. Workの将来launch操作はremote readiness headがその承認SHAと完全一致することをread-only確認。
3. approved parentのworkflow/plan/fixtureのraw SHA256とschemaを読み、固定marker内容を構成。
4. single parent = owner承認SHAのmarker-only commitを作り、同branchだけを非force更新。
5. **marker commit成立を消費点とする。push・workflow作成・setupより前に消費済み。**
   commit作成後のpush失敗/unknownにも新しいcommitを作らずSTOP。承認は一回限り。
6. runnerはevent.before = direct parent = marker.approved_parent_shaを検証。
   current commit diffはexact markerのAdded 1件のみ。parent treeにもmarkerなし。
7. immutable parent SHAで全historyをページ取得しrootまで全parent edgeを確認。
   baselineがancestorであることを確認。同marker pathの全過去変更historyが1件でもあればSTOP。
8. current runはattempt 1、exact workflow/path/branch/SHA/eventをsecondary照合。
   branch tipは検証の前後ともlaunch SHAと一致することを要求。
9. guardが成功した時だけallow/execution_approvedのstep outputをtrueにする。
   Python setup、runtime情報確認、固定container操作より先にguardを終える。

owner承認はこの会話の明示承認とWork launchのexact parent照合で表現する。
marker自身のbooleanやtimestampだけでowner承認があったことを証明したとは扱わない。
preparation commitは自身のSHAを埋め込まない。将来markerが外からexact parentをpinするため
self-referenceはない。launch commitでcode変更・権限変更・policy flag変更はしない。

normal retry/cancel/setup failure/timeout/unknownでは消費を取り消さない。
automationにdelete/update/reset/reuse/resume経路はない。workflow tokenはcontents/actions readだけ、
checkout persist-credentials false。marker書込権限を与えない。

Modified/Deleted/multiple-file diffはSTOP。delete→re-addも過去path historyでSTOP。
API error/pagination failure/duplicate/ambiguous/scan bound超過はSTOP。
forced push、branch tip drift、baseline不在、ancestor edge欠落、cycle、disconnected historyは
`BLOCKED_HISTORY_CONTINUITY_LOST`。自動resetは禁止。

これはadminにも絶対削除不能なcryptographically immutable ledgerではない。
owner/adminがbaselineを含む履歴を故意に改変し、GitHubと承認外のlaunch操作も操作した場合、
GitHub-onlyでは完全な検知・削除不能を保証できない。検知できたcontinuity lossでは必ずSTOP。
この限界とautomationの自動retry防止を混同しない。

## Marker schemaと独立identity

schema: `readiness/branch-marker-schema.json`。marker file自体は今回存在しない。
追加propertyは禁止、required 9 fields、SHAは40/64桁、once/no_retry/no_resumeはboolean true。

| kind | identity / exact marker path |
|---|---|
| runtime-preflight | `manual-fixture-runtime-preflight-20261004-001` / `audit-evidence/consumed/manual-fixture-runtime-preflight-20261004-001.json` |
| actual-render | `manual-fixture-render-20261004-001` / `audit-evidence/consumed/manual-fixture-render-20261004-001.json` |

workflow_sha256は対応workflowのraw bytes、plan_sha256は対応policy/planのraw bytes、
fixture_sha256はrender-payload.canonical.jsonのraw SHA
`2b92b1b2266da9be38e0cebdd061add724734049f08afc0bbffbe06b7aa53c40`。
script/normalizedのSHAもCLIで既存全3ファイルと照合する。
preflightとrenderは別path・別identity・別kind・別concurrency。互いのidentityを消費しない。

## Runtime範囲と旧モデル

preflight: GitHub-hosted ubuntu-24.04、Python 3.12.15、FFmpeg/ffprobeとfilter/encoder availability、
Noto CJKのversion/selected fontだけを確認。apt install/latest fallbackなし。
固定VOICEVOX AMD64 digest pull/start後、GET /versionとGET /speakersを各1回。
version=0.25.2、style ID=1、ずんだもん/あまあまの完全一致を要求。
no retry/resume。synthesis/encode/MP4/artifact/cache/D1/Worker/AI/YouTube/SNSは0。
`cloud_runtime_preflight.py` CLIは必ずprimary marker guardを使う。
旧history_gate/approval_gateは既存guardedテストの比較用offline oracleとして残す。
実CLIに旧ledgerへのfallbackはない。
policyのallow=false/execution_approved=false/hard_disabled=trueは準備状態の記録として維持。
新CLIの承認経路は別commitの完全検証済みmarkerだけ。markerなしで解除できない。
render candidateはhard-disabled。共有guardとoffline oracleだけ準備し、live adapterは実装しない。
preflight PASSはrender承認を代替しない。render markerは別の最終承認後のみ作成。
既存Quality Gateとproduction sourceの数値は維持。
render planのconsumption fieldだけ後継方式に更新し、そのraw hash lockを更新する。

## Billing/artifact

本人提供2026-10-04 evidenceを維持: Actions/Packages budget $0 / Stop usage Yes、
保存済みpayment methodは画面表示範囲になし、Oct 1–4 billed amount $0。
Workで設定を変更しない。card追加・paid upgrade・budget変更は禁止。
将来render artifactはshort.mp4/payload_snapshot.json/render-result.jsonのみ、total <=12 MiB、
retention 1 day、upload max1。over-cap/quota/upload failure/unknownは再uploadなしSTOP。
free quotaを超えbillable保存が必要なら保存失敗としてSTOP。

## 今回の検証

追加testsはmarker/complete ancestry/API adapter/marker oracle/runtime-before-guardを検証。
テスト内markerはmemory上だけ。対象pathを作らない。
既存test件数を維持し、旧trigger/consumption assertionsだけ新仕様に置換。
guarded Python/Nodeはseccomp no-exec/no-socket、media write/import拒否。
remote readiness更新はoffline code/tests/docs/hash manifestだけ。
marker pathがdiffにないためpreflight push filterに一致せず、runtime workflow起動0。
main/production/n8n/V1/YouTube Pipeline/PR15/PR16には操作しない。
CI headとremote read-back・run evidenceは最終回答で報告する。
