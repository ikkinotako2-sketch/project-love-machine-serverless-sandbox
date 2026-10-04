# Runtime preflight 002 offline preparation

今回の基準headは `f341bf35a7a8bdca5e1a96931783459ade2675cc`。
readiness branchだけ変更する。mainは `8ac2337a37072ae23f7781e2f47e8dfc7016b30f` を維持。
001 markerのblobは `840339c827253d8d9a15efb53983e358c4bb4ed6` のまま。
001 run `37207981665` attempt 1 FAILUREは永久audit evidenceとして保持し、rerunしない。
actual render markerと新002 markerは未作成。002承認はまだない。

## Read-only forensicとroot cause範囲

launch commitの親は承認済みhead、diffは001 marker Added 1件。marker/history guard成功、
GitHub-hosted Ubuntu 24.04.5 / image 20260927.320.1、Python 3.12.15 setup成功をjob logsで確認。
metadata-only stepだけ失敗。旧 `cloud_runtime_preflight.py` の `process()` は、
FileNotFoundError / CalledProcessError / TimeoutExpired 等の**全subprocess例外**を
`RUNTIME_COMMAND_FAILURE_OR_UNKNOWN` にまとめ、command/stage/return codeを保存していない。
旧finallyのcleanup失敗も元のerrorを覆う可能性がある。
したがって既存runから失敗command、Docker pull/start、metadata GET到達を断定できない。

優先して確認すべき候補は ffmpeg/ffprobe executable不足、dpkg-query対象packageの一部不足
（複数packageを一括queryするため1つ不足でも失敗し得る）、fontconfig/fc-match不足、
Docker daemon/queryの失敗。pull/inspect/start/wait/cleanup failureも旧code上の候補として残る。
これは推論であり、root cause確定ではない。READMEにないことは不在証明ではない。
旧runのraw stderr/stdout/provider bodyは新evidenceにコピーしていない。

## Official runner image比較

[固定公式README](https://github.com/actions/runner-images/blob/ubuntu24/20260927.320/images/ubuntu/Ubuntu2404-Readme.md)
を2026-10-04にread-only取得し、OS/image versionを照合。
Docker Client/Server 28.0.4の記載はあるが、以下の要求をREADME単独では証明できない。

| 要求 | 固定READMEによるpreinstall証明 | 002で確認すること |
|---|---|---|
| FFmpeg executable | 未証明 | `ffmpeg -version`、6.1.1一致 |
| ffprobe executable | 未証明 | `ffprobe -version`、6.1.1一致 |
| ffmpeg package | exact 7:6.1.1-3ubuntu5は未証明 | dpkg-query exact一致 |
| fonts-noto-cjk | 未証明（color-emojiは別package） | exact 1:20230817+repack1-3、selected font/path |
| libx264-164 | 未証明 | exact package、libx264 encoder |
| libass9 | 未証明 | exact package、subtitles filter |
| required filters/encoders | 未証明 | 全FILTERS、libx264/aacが揃うこと |

READMEは完全なfilesystem/package inventoryではない。全項目をruntimeで確かめる。

## 002 diagnosticsとeffect boundary

新identity: `manual-fixture-runtime-preflight-20261004-002`
新path: `audit-evidence/consumed/manual-fixture-runtime-preflight-20261004-002.json`
新workflow: `.github/workflows/plm-cloud-runtime-preflight-v2-once.yml`
branch + exact marker pathのpushだけ。contents/actions read、persist-credentials false。
markerなしではruntimeに進まない。001用cloud/launch guardは常に `IDENTITY_CONSUMED_001`。
002、001、actual renderは別identity/marker。001 marker/runはdelete/reset/renameしない。
同じAUTOMATION_MONOTONIC_CONSUMPTION/direct-parent/marker-only Added/history guardを適用する。
002も失敗/unknownなら消費を戻さず、retry/rerun/resume/second launchは0。

固定stage labelをsubprocess/GET前にflushしてjob logとsummaryへ記録する。
保存するのは固定label、pass/failed/mismatch、範囲制限済みreturn code、期待値一致だけ。
stdout/stderr/command/exception text/token/provider/raw speakers bodyは保存しない。
実行commandは固定tableのみでcredential argumentを受け取らない。

| Stage | Safe failure code |
|---|---|
| python_version | RUNTIME_PYTHON_VERSION_FAILED |
| ffmpeg_version | RUNTIME_FFMPEG_VERSION_FAILED |
| ffprobe_version | RUNTIME_FFPROBE_VERSION_FAILED |
| package_query | RUNTIME_PACKAGE_QUERY_FAILED |
| filter_query | RUNTIME_FILTER_QUERY_FAILED |
| encoder_query | RUNTIME_ENCODER_QUERY_FAILED |
| font_query | RUNTIME_FONT_QUERY_FAILED |
| docker_version | RUNTIME_DOCKER_VERSION_FAILED |
| docker_pull | RUNTIME_DOCKER_PULL_FAILED |
| docker_inspect | RUNTIME_DOCKER_INSPECT_FAILED |
| docker_start | RUNTIME_DOCKER_START_FAILED |
| startup_wait | RUNTIME_STARTUP_WAIT_FAILED |
| engine_version_get | RUNTIME_ENGINE_VERSION_GET_FAILED |
| speakers_get | RUNTIME_SPEAKERS_GET_FAILED |
| docker_cleanup | RUNTIME_DOCKER_CLEANUP_FAILED |
| registry_get | RUNTIME_REGISTRY_GET_FAILED |

Python/binaries/packages/filters/encoders/font/Docker availabilityを順に全確認してから
registry metadata / Docker pullへ進む。先行gate失敗ならpull=0。
各effect最大1回。cleanupはstartのunknownも含め最大1回で、元のfailureを覆わない。
cleanupだけ失敗の場合もPASSにしない。GET /version,/speakersは各1回、生成endpointなし。
summaryへ保存するspeaker情報は固定期待値と照合結果のみ。
package mismatch/filter missing/font fallbackを個別stage errorにする。

## Exact package候補・別承認

[Ubuntu noble ffmpeg](https://packages.ubuntu.com/noble/amd64/ffmpeg)は7:6.1.1-3ubuntu5、
[fonts-noto-cjk](https://packages.ubuntu.com/noble/fonts-noto-cjk)は1:20230817+repack1-3。
[libx264-164](https://packages.ubuntu.com/da/noble/libx264-164)は2:0.164.3108+git31e19f9-1、
[libass9](https://packages.ubuntu.com/en/noble/amd64/libass9)は1:0.17.1-2build1。
公式repository/version evidenceで候補を設計した。runnerへのpreinstall証拠ではない。
package SHA256/dependency closureは未取得、install-readyとは主張しない。

`runtime-preflight-v2-package-plan.json` は**別承認を要する非実行設計**。
必要ならGitHub-hosted runnerだけで、公式Ubuntu署名index/version/architecture/SHA256を
固定してdependency closureもレビュー後にinstallする。apt latest/PPA/Pro/有料サービス/
ユーザーPC/fallbackは禁止。availableでないversionや新依存はSTOPして別planにする。
**今回の002 candidateはobserve-only。install action/codeは含めない。**
不足があれば具体的stageでSTOPし、無断installしない。installを含む候補は別code準備・別承認が必要。

## Verification

Work cloudでguarded offlineテストのみ。seccompで実exec/network/media writeを拒否、
new testsはin-memory fakeのみ。今回runtime subprocess、Docker、VOICEVOX、FFmpeg、
合成、encode、MP4、artifact、D1/Worker/AI/YouTube/SNS/user PCはすべて0。
offline CIだけ許可。002 marker未追加なのでruntime workflowのpush pathに一致しない。
prepared codeと将来marker-only launchは分離する。実render承認へは進まない。
