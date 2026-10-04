# 003 exact Ubuntu package plan — BLOCKED

準備基準head: `5290f3c6890b58b934f18dba04de38454e104f6e`。
001/002 markerはblob `840339c827253d8d9a15efb53983e358c4bb4ed6` /
`8ba2410f0bdc9cbf0eba4316584ba102bc26d0e6` のまま永久保持。
001 run 37207981665、002 run 37210057371をrerun/retry/resumeしない。
002の確定証拠はmarker/history PASS、Python 3.12.15 PASS、
`stage=ffmpeg_version` → `RUNTIME_FFMPEG_VERSION_FAILED`。
ffprobe以降未到達、Docker/VOICEVOX/合成/encode/MP4/artifactは0。
ffmpeg起動失敗の具体的exceptionは断定しない。

003: `manual-fixture-runtime-preflight-20261004-003`。
marker候補は `audit-evidence/consumed/manual-fixture-runtime-preflight-20261004-003.json`。
marker未作成。actual render markerも未作成。main/productionは変更しない。

## Fixed root package candidates

Ubuntu公式InReleaseとmain/universe Packages.xz metadataから以下を記録。
gpgvでUbuntu Archive Automatic Signing Key (2018)の署名を検証し、両index SHA256をInReleaseと照合。
.debをdownloadしていない。package managerもruntime binaryも実行していない。

| Package | Exact version | Architecture | Component |
|---|---|---|---|
| ffmpeg | 7:6.1.1-3ubuntu5 | amd64 | universe |
| libavcodec60 | 7:6.1.1-3ubuntu5 | amd64 | universe |
| libavfilter9 | 7:6.1.1-3ubuntu5 | amd64 | universe |
| libavformat60 | 7:6.1.1-3ubuntu5 | amd64 | universe |
| libavutil58 | 7:6.1.1-3ubuntu5 | amd64 | universe |
| libswresample4 | 7:6.1.1-3ubuntu5 | amd64 | universe |
| libswscale7 | 7:6.1.1-3ubuntu5 | amd64 | universe |
| fonts-noto-cjk | 1:20230817+repack1-3 | all (amd64で使用可) | main |
| libx264-164 | 2:0.164.3108+git31e19f9-1 | amd64 | universe |
| libass9 | 1:0.17.1-2build1 | amd64 | universe |

これはNoble **release pocket**の候補。current security/updatesを適用済みとは主張しない。
同じ署名済みrelease index cohort（2024-04-25）で10件を照合済み。ESM/Proや別versionへ自動切替しない。
fonts-noto-cjkはarchitecture-independent `all`であり、amd64と偽記しない。
plan JSONにofficial repository、suite/pocket、filename、version、architecture、component、
10件すべてのSHA256とDepends/Pre-Dependsを記録した。
`runtime-preflight-v3-package-index-evidence.json`に247件の推移依存候補のexact metadataを保存。
これは全代替候補を列挙した記録であり、選択済みinstall closureではない。
署名鍵fingerprint: `F6ECB3762474EDA9D21B7022871920D1991BC93C`。
公式keyring: https://archive.ubuntu.com/ubuntu/project/ubuntu-archive-keyring.gpg
公式index: https://archive.ubuntu.com/ubuntu/dists/noble/InRelease

主な公式metadata入口:
- https://packages.ubuntu.com/noble/amd64/ffmpeg/download
- https://packages.ubuntu.com/noble/all/fonts-noto-cjk/download
- https://packages.ubuntu.com/noble/amd64/libavcodec60/download
- https://packages.ubuntu.com/ja/noble/amd64/libavfilter9/download
- https://packages.ubuntu.com/noble/amd64/libavformat60/download
- https://packages.ubuntu.com/en/noble/amd64/libavutil58/download
- https://packages.ubuntu.com/noble/libswresample4
- https://packages.ubuntu.com/noble/amd64/libswscale7/download
- https://packages.ubuntu.com/da/noble/amd64/libx264-164/download
- https://packages.ubuntu.com/en/noble/amd64/libass9/download

## BLOCKED_PACKAGE_DEPENDENCY_CLOSURE

指定10件はdependency closureではない。ffmpeg自体がlibavdevice60/libpostproc57/
libsdl2-2.0-0等を要求し、libavcodec60/libavfilter9には多数のcodec/font/graphics依存がある。
`runtime-preflight-v3-direct-dependencies.json`に公式detailsページの直接依存・version constraint・
architecture qualifierを記録した。alternatives、Pre-Depends、transitive closureは未解決。
これはHTMLの人間向け宣言を保存したもので、完全なDebian dependency resolverとは扱わない。

未解決点:
1. 全dependencyのversion constraint、alternative/virtual provider選択の検証。247候補の列挙を解決済みとは扱わない。
2. runner base package inventoryとversion constraintの実証。READMEだけで充足済みにしない。
3. install resolverが追加/upgrade/remove/downgradeするpackageをすべて列挙したtransaction proof。
   release snapshotのlibc等を現在runnerへ無条件導入・downgradeしてはならない。
4. verified download/hash/install/live adapterは未実装。closureが未確定なため先に書かない。

root10件のSHA/filenameと署名済みindexは確定済みだが、上記が残るため実行準備PASSにしない。

したがってworkflowは `if: false`、allow/execution_approved=false。
CLIはeffectなしでBLOCKED。003 schema/branch/pathは準備したがlaunch可能とは報告しない。
001/002 cloud guardは各IDENTITY_CONSUMED_001/002で常にSTOP。

## Future install design — not executable yet

apt-get updateが必要になる可能性をplanに明記した。将来承認されたcloud-only adapterでは、
専用source listを official `https://archive.ubuntu.com/ubuntu` / Noble main+universeだけに制限し、
Ubuntu archive signing keyでInReleaseを検証、対応Packages/by-hashの固定SHAを照合する。
mutable update直後のunversioned installは禁止。PPA/third-party/snap/latest/Pro/有料runnerなし。
update/indexが固定snapshotと一致しなければ `RUNTIME_APT_INDEX_FAILED` でSTOP。

install designは全dependencyを `package=exact-version` 形式で固定。
`--no-install-recommends`でoptional recommendsを増やさない。Depends/Pre-Dependsは削らない。
`--no-download`でverified archive以外をinstall中に取得させない。
`--no-remove`/`--no-upgrade`候補は意図しないbase変更をSTOPさせるため。version競合時に
自動downgrade/fallbackしない。これらのflagで成功するtransactionを証明するまではBLOCKED。

download候補は各fixed official filenameのみ。binary SHA256とdeb control name/version/archを
確認し、resolver transactionとfull closureを照合してからinstallへ進む。
artifact/cacheに保存しない。今回はapt update/download/installを一切行っていない。

## Offline code and stage model

`cloud_runtime_preflight_v3.py`はguarded in-memory offline oracleだけ。
install_argumentsは純粋な候補文字列生成で、subprocess/HTTP adapterなし。
synthetic testsのcomplete graphは**Ubuntu evidenceではない**。
安全gate・failure mapping・順序を検証するための架空データであり、real planは必ずBLOCKED。

追加safe codes:
- RUNTIME_APT_INDEX_FAILED
- RUNTIME_PACKAGE_DOWNLOAD_FAILED
- RUNTIME_PACKAGE_HASH_FAILED
- RUNTIME_PACKAGE_INSTALL_FAILED
- RUNTIME_PACKAGE_VERSION_MISMATCH
- RUNTIME_DEPENDENCY_CLOSURE_MISMATCH

002 stage codesを維持。固定stage/return codeだけのlogs。secret-like stderrは非出力。
将来の順序候補は marker/history → hosted runner → Python → index/source/hash/closure →
exact download → verify binary/control/hash → exact install → package version/closure照合 →
Python/FFmpeg/ffprobe/packages/filters/encoders/font/Docker availability全確認 → registry →
fixed digest pull/inspect/start → version/speakers各GET1回 → cleanup最大1回。
どのinstall/runtime gate失敗でもDocker pull=0。no retry/rerun/resume。
生成endpoint・encode・MP4・artifact・publishingは含めない。

## Checks / operation boundary

offline testsはnative seccomp no-exec/no-socketのWork cloud内だけ。
全runtime effects、package download/install、003 marker、actual-render markerは0。
GitHub offline CIのみ起動する。runtime pathはdiffに含めず、workflowもhard-disabled。
closureが完全に固定され、installerを準備して新CIを通すまではlaunch承認を求めない。
