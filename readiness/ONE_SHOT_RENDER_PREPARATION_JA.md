# 固定fixture one-shot render preparation

**BLOCKED_RENDER_PREPARATION** — 最初の停止gateは `BLOCKED_RENDER_RUNTIME_UNPINNED`。実render実行承認を求める段階には到達していない。

対象: sandbox readiness branch `plm-offline-readiness-v1-20261002`。production、sandbox main、V1、n8n、既存Pipeline、PR #15/#16は変更しない。調査日: 2026-10-04。

## 固定候補

Render identity: `manual-fixture-render-20261004-001`。Fixture: `manual-japanese-script-fixture-v1`。既存fixtureを再生成・変更していない。

- script SHA256: `9077ccd4b61ff3bcdadcccaaea90219377acfd4abf19ebd414af36f7eb7c0b8b`
- normalized contract SHA256: `dbcc62dfe12ef550bb37987839c6cd3e30743ca9bc307d6f8131d42e7e0f555e`
- render payload SHA256: `2b92b1b2266da9be38e0cebdd061add724734049f08afc0bbffbe06b7aa53c40`
- preparation plan raw SHA256: `3a39c4a15ebf9868d7d49a6f34e412c07827aaac22f12814a4f3b6d0fecfe246`

## Production source固定

最新mainのread-only調査で得たcommitは `25f24bc4e6a20164c5549f746fc0eefcedf5d178`。Repository: `ikkinotako2-sketch/project-love-machine`。候補workflowはこのcommitを `.preparation/production-render` に明示checkoutする。Reusable workflow呼出しだけには依存しない。

JSONのsource snapshotはcompile/AST照合用のread-only資料であり、sandboxに実行可能なrenderer forkを作らない。将来の実行source-of-truthもproduction固定commit。Snapshot自体の完全性はraw SHAで照合する。候補には実行executorがなく、現在はcheckout後もSTOPする。

| File | raw SHA256 |
|---|---|
| `.github/workflows/render-short.yml` | `d2a02202245c222a4b9a0622ba3c2f17c174e0ea478cf84b2180bb72b4e6a573` |
| `render-worker/RENDER_QUALITY.md` | `9ef585ab5530cac5d41808442ff0372ee42ea95455a5e1b208d6f4f9e2fa12ef` |
| `render-worker/ffmpeg_builder.py` | `8f542b06c2b98a7beb09a2798969fb4def8673efd73e673db6ebce176aedbccc` |
| `render-worker/quality_gate.py` | `f3cbc58d62d0cfda41997fe8d420a3a630173effcbbfcbc397b0063cf14400ec` |
| `render-worker/render.py` | `993a89b8117b2cbb12be3409891a95beea22d9a64c56d93fe710f97ecd62640b` |
| `render-worker/voicevox.py` | `d9811c6d49fdd312fd6a8f6d51514a8e0accfb46cc1cf2e07988d9c43cbfd858` |

## Runtime / $0 gates

- Standard GitHub-hosted x64 `ubuntu-24.04` を候補に固定。Public repositoryでstandard runner computeは無料。Larger/paid runnerを使わず支払方法追加を要求しない。
- Artifact storageはaccount内の共有使用量・月内累積使用量も関係するため、public compute無料だけで全体$0とは判定しない。現accountのstorage budget証拠は取得できておらずSTOP。
- Artifact候補は `short.mp4` / `payload_snapshot.json` / `render-result.json` の3ファイルのみ。固定name `rendered-short-manual-fixture-render-20261004-001`、retention 1日、合計12 MiB以下、raw audio/cacheなし。この上限だけで料金0を証明できるとは主張しない。
- VOICEVOX公式engine release候補 `0.25.2` を確認。しかしimmutable OCI manifest/index digestは公式registry metadataから取得・検証できていない。Image/config/layer URLにあるSHAをpull digestとみなさない。`cpu-latest` 不使用。Version tagだけではgateを通さない。
- Python候補 `3.12.15`。setup-python配布binary availabilityは未検証。FFmpeg package exact version/digestも未検証で、apt最新へfallbackしない。Font package候補は Ubuntu noble `fonts-noto-cjk=1:20230817+repack1-3`。Hosted OS image自体の更新も残るためbit-for-bit再現性は主張しない。
- Actionsはcommit pin: checkout `3d3c42e5aac5ba805825da76410c181273ba90b1`、setup-python `5fda3b95a4ea91299a34e894583c3862153e4b97`、upload-artifact候補 `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`。現在upload stepは存在しない。

公式根拠:

- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://github.com/VOICEVOX/voicevox_engine/releases/tag/0.25.2
- https://hub.docker.com/r/voicevox/voicevox_engine/tags
- https://packages.ubuntu.com/noble/fonts-noto-cjk
- https://www.python.org/downloads/release/python-31213/

## speaker 1利用条件

公式VVM `0.16.2` のREADME固定commit `a557dd4661103f206f7cd7d81e0c9a9b26253372` でID1は「ずんだもん / あまあま」。ただし予定engineのimmutable containerが未固定なので、そのcontainerの `/speakers` metadata照合は未実施。Engine起動も合成も0。

現在の公式規約では動画・YouTube・商用/非商用利用はクレジットと各音声libraryの条件に従う。クレジットは `VOICEVOX:ずんだもん`。候補のrun summaryとrender-resultに記録し、将来公開する場合は動画説明欄等に表示する。今回の一般的なoriginal fixtureのみを監査対象とし、政治・宗教、誤認を意図した情報等の禁止用途を包括承認しない。

自動生成動画全般の明示禁止は確認していないが、これを無条件の自動化承認とは解釈しない。現在render pathの音声後処理（loudnorm/apad/atrim）について明示的な許諾根拠を確認できていないため、音声加工可否をPASSにしない。禁止を断定したという意味ではなく、要求された確実性が満たされていない。別speaker選択・hash変更・有料licenseは提案しない。

公式根拠:

- https://github.com/VOICEVOX/voicevox_vvm/blob/a557dd4661103f206f7cd7d81e0c9a9b26253372/README.md
- https://voicevox.hiroshiba.jp/term/
- https://voicevox.hiroshiba.jp/qa/
- https://zunko.jp/con_ongen_kiyaku.html

## Offline pre-render検証

Fixture narration、scene/caption順序、1080×1920/30fps、speaker=1、external BGM/SFX assetなしを既存canonical payloadと照合。展開予定envのsafe snapshotを `one-shot-render-env.json` に固定しsecret/provider credential fieldを禁止する。

固定production Python4ファイルをcompileのみで確認し、ASTでstdlib/local dependencyを照合。Exact production FFmpeg builder ASTをoffline fixtureで使用し、subprocess runner・duration probe・Path writeをin-memory stubへ置き換えてcommand/ASS contractを検証した。FFmpeg/ffprobeを実行せず、音声・画像・MP4を作らない。

Command構築、caption order/timing、字幕Dialogue、resolution/fps、workspace内output、外部URL/任意path/外部音楽なしをテストした。このmock command検証は実codec、Docker、binary availability、実Quality Gate成功の証明ではない。

## Quality Gate固定

Production `quality_gate.py` の固定sourceをoffline AST fixtureで検証:

| 条件 | 固定基準 |
|---|---|
| MP4 | file存在、productionはsize >=10,000 bytes |
| one-shot追加最小size | >10,000 bytes（将来実executor実装時に追加、現時点は候補条件） |
| stream | video/audio両方存在 |
| 解像度 / fps | 1080×1920 / 正確に30 |
| duration | 0.5〜180.5秒、両端含む |
| subtitle | captions.assがfile、Dialogue:が存在 |
| decoded brightness | decoded frame YAVG最大値 >=25 |
| audible audio | mean volume >= -38 dB |

閾値の実行後変更は禁止。Boundary/rejection testsで現sourceのinclusive条件も確認した。ASSは将来の作業用fileでありupload artifactではない。

## One-shot / unknown方針

初回承認runからidentityを永久consumedとする候補。Setup/checkout/pull/start/synthesis/encode/Quality Gate/uploadの失敗でもretry/resend/fallback/二度目render/rollback=0。Unknown時はread-only run/artifact reconciliation最大1セット後STOP、結果が分かってもresumeしない。永続consumption ledgerとprior-run確認の実executorは未実装で、準備PASSとは扱わない。

新workflow `plm-manual-fixture-render-prepared-once.yml` はhard `if: false` / allow=false / execution_approved=false。Docker/start/synthesis/FFmpeg/upload実行stepはblocked中は追加しない。旧workflow・既存証拠row・provider-neutral migration candidateは変更していない。

## CI / 操作境界

既存testsを維持し新Python tests 27件追加。Local guarded CI: Python625 PASS、Node948 PASS（GitHub側は実runの件数を別receiptで記録）。Native guardはsocket/execを拒否し、render execution/external API calls=0を記録した。

AI、D1 remote read/write、migration apply、Worker、Docker pull/start、VOICEVOX synthesis、FFmpeg encode、MP4、YouTube、SNS、credential create/registerすべて0。TEST_ONLY/DRY_RUN/NO_PUBLISH/EMERGENCY_STOP=true、live_ready=false / posting_permitted=false。

**実renderはまだ実行せず、承認要求も行わない。** 最初に必要なのは公式registryによる0.25.2のimmutable pull digestの検証である。新credential/card/別accountは要求しない。Digestが解決しても、残るstorage budget・固定container speaker metadata・音声後処理条件・runtime binary・one-shot executor gatesを満たすまでBLOCKEDを維持する。
