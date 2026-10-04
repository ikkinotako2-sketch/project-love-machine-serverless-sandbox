# Manual Japanese fixture → checkpoint → render input — offline audit

**PASS_MANUAL_FIXTURE_OFFLINE_WIRED**。これはmanual inputの共通generation JSON境界→temporary SQLiteのmanual checkpoint reference→現在のproduction render入力contractのoffline PASS。remote backendへmanual importできること、実MP4が生成/品質確認済みであることを意味しない。

固定identity: `manual-japanese-script-fixture-v1`。本作業で新規作成した固定テスト台本「机の上に、小さな余白を」。API出力・既存動画・歌詞・CM・copyright素材からの引用ではない。3 scenes、0–6 / 6–12 / 12–18秒。背景はrenderer内のローカル図形、BGM assetなし、sfx=none。fixture内容とhashは固定し、失敗しても修正・再生成・再送しない。

## コードを根拠に固定した現在のcontract

production source pin: `25f24bc4e6a20164c5549f746fc0eefcedf5d178`。GitHub mainの実ファイルを読み取り、`manual-fixture-production-sources.json`へ非secretコードsnapshot、`manual-fixture-source-pins.json`へ各raw SHAを保存。production / main / PR15/16 / V1 / n8nへの変更は0。source snapshotは実行許可ではない。

production repositoryにはscript inference/generation runtimeやn8n structured parser本体はない。generation shapeは既存sandbox `generation_contract.py`のdata-only schemaと、保存済みn8n Set/dispatchの**コード**を使用し、current production render consumerの実コードへ実際に渡して照合した。live n8nの現在状態を調べたとは主張しない。保存済みn8nコードと現在のproduction consumerを区別する。

| Field | generation result | 現在のproduction render codeでの使用 |
|---|---|---|
| output | wrapper内の台本object。title/hook/narration/scenes/bgmのexact 5 fields | render payloadのoutputは別物：format=mp4 / 1080×1920 / 30fps。wrapperを漏らさない |
| title / hook | 必須・空白だけ不可 | load_payloadが保持。現build_videoはタイトル/hookを描画せず、VOICEVOXにも連結しない。YouTube Pipelineはtitleをupload metadataへ渡すが今回は投稿しない |
| narration | 必須string、変更しない | render.main→generate_voiceに全文そのまま渡す。今回TTSを呼ばない |
| scenes | 順序付きarray、caption/start/end等 | _segmentsがstartでsortし最大24 scene。今回adapterは事前に単調・非重複・24以内を強制し、silently truncationしない |
| visual_keyword | 各sceneで必須、120文字以内 | ローカル図形motifとpalette hashに使用。URL取得や素材検索ではない |
| captions | generationには含めずsceneから導出 | index=i+1 / start_seconds / end_seconds / text。_write_assが字幕を生成。空caption、時刻不正、参照不一致はadapterで拒否 |
| emphasis_words | sceneのcaptionに実在する語、各30文字以内 | _captions_with_scene_emphasisが時刻/文言一致したsceneからcaptionへ継承し、_caption_textがescape後のASS強調を作る |
| emphasis | 新generation contractには認めないalias | rendererはcaption/sceneのlegacy fallbackとして読む。fixtureはcanonical emphasis_wordsのみ |
| motion | 固定fixtureはnone | 現build_videoはこのfieldを読まず、独自crop motionを使う。指定motionが再現されるとは主張しない |
| sfx | sceneにはnone | scene.sfxを現audio pathは読まない。top-level/bgmsfx.assetだけbundled license sidecar付きで読む。今回は双方不使用 |
| bgm | mood/volumeのみ、fixture volume=0 | 現rendererはassetがある場合のみaudioを混ぜる。mood/volumeは現在audio選択・gainに使われない。fixtureにassetなしなので無音BGM |
| speaker | generation fieldではなくadapterでinteger 1 | workflowはstring "1"→load_payloadがint→VOICEVOX speaker/styleへ。speaker 1の将来利用条件は実render準備gateで確認 |

`youtube-pipeline.yml`のrender jobは9 inputsだけをrender-shortへ渡す。fixture adapterはこの9 fieldを固定し、OAuth/YouTube/provider metadataを含めない。renderのload_payloadは8 content fields（render_idはworkflow/artifact識別用）を読む。1080×1920/30fpsはffmpeg_builderの実guardとquality_gateの実checksでも一致している。

## strict JSON / canonicalization

raw UTF-8をstrict decode、JSON object / wrapper exact {output} / nested required fields exact、unknown field拒否、strict型（boolをnumberとしない）、required text非空、schema limits・配列limits・scene時刻単調/非重複を確認。raw/scriptとも65,536 bytes以下。control chars、bidi controls、unpaired surrogate、malformed JSON、duplicate keys、NaN/Infinity/overflow/depth、path/URI/外部asset fieldを拒否。

sceneの上限24、visual_keyword120、emphasis30はcurrent production rendererによる切捨てを防ぐ**sandbox adapterの狭い受入制約**。rendererの公開最大値やlive AI parserの制約を推測したものではない。schemaのその他boundsも既存offline project contractを使用する。

canonical bytesはUTF-8 / sorted key / compact JSON / no trailing newline / finite numbers。整数値のfloatは整数へ、negative zeroは0へnormalizeする。空白/key order/Unicode escapeの非意味的差異ではscript hashは変わらない。array orderは保存。Unicode本文はNFC等へ書き換えずcodepointを保持し、文言変更は別hash。

既存`generation_contract.canonical()`や旧receipt/hashは変更しない。新manual boundaryだけの明示的versioned number-normalizationであり、既存6.0表現を保存した旧raw/hashを再hashしない。DBに保存したscript_jsonはcanonical **raw bytes**もexact一致を要求し、reload時は再validation＋hash照合。semantic hashとraw fixture SHAを分ける。

input/request contract hashは入力schema/limits/renderer output仕様のhash。manual request hashはsource/identity/input contract hash/normalized output hashの固定envelopeであり、AI API requestが存在するという意味ではない。

| 固定hash | SHA256 |
|---|---|
| script_sha256 | `9077ccd4b61ff3bcdadcccaaea90219377acfd4abf19ebd414af36f7eb7c0b8b` |
| input_request_contract_sha256 | `81ff6c8abd18453677635df65308ef6059e9c4e1af870bc501510f5262d4d337` |
| manual_request_sha256 | `8c68e99291646a7599fc017456341497e29138e86b90c28ac3c0ccd729cd1971` |
| normalized_contract_sha256 | `dbcc62dfe12ef550bb37987839c6cd3e30743ca9bc307d6f8131d42e7e0f555e` |
| normalized_output_sha256 | `06b35f1c9a2983c2f5be05bf0f0f3062a84fcf96e2775610a947ee67ecbe450f` |
| render_payload_sha256 | `2b92b1b2266da9be38e0cebdd061add724734049f08afc0bbffbe06b7aa53c40` |
| checkpoint_sha256 | `c15e07c6533c95d061808696d5f1962c7d9ae9f4dade0e69abe126a2d1f86333` |
| raw_fixture_sha256 | `abfe32ed5d515f7e4672c52c05340507d0de296eeadbc2366c53e45f0a3f34f4` |

## checkpointとprovider identityの分離

normalized resultはsource=`manual_fixture`、provider_identity=null、model_identity=null。provider response parserは一切通さない。SQLite `offline_manual_checkpoint` は**temporary reference専用**で、STARTED/version1→検証→SHA→CAS COMPLETED/version2→commit→full read-backを実行する。temporary file SQLiteのcommit後にconnectionを閉じて再openしても同じcheckpointとrender payloadへ復元できることを証明する。request identityもimmutable。unknown/failure/mismatchはdeterministic STOP、再生成・自動補修なし。

重要な実装境界：固定provider-neutral migration候補の `plm_rt_v2_script` はprovider/modelがNOT NULLで、COMPLETED transitionにはGENERATION effect SENT/UNKNOWNを要求する。manual import用のschemaではない。sourceを架空のprovider名にしたり、実施していないgenerationをSENTと記録したりしない。今回manual reference tableを**offlineだけ**に設け、candidate migrationは4 raw SHAを含め一切変更していない。将来のremote manual import仕様は別途設計・承認が必要で、このPASSからremote write許可は生じない。

candidate exact SQLをtemporary SQLiteへ適用し、5 tables / 11 triggers / 14 autoindexes、新namespace初期0 rows、旧証拠/schema不変を既存testsと新testsで確認。異なるsynthetic provider identifier probeを受理してもschema変更が不要なことを確認したが、providerを選定/認可したものではない。manual checkpoint作成時はv2 candidate全5 tablesを0 rowsのまま保持し、v1/v2/v3旧audit evidence row、stage2成功3 row、atomicity、test_jobsを完全保持。_cf_KVはschemaのみ、content対象外。

## checkpoint → render inputの実照合

COMPLETED checkpointをfull validationし、script/request/contract SHAを照合してから既存parity adapterでcaptionを導出しrender payloadへ変換。narration/title/hook/scene order/caption orderを保持。captionはsceneの時刻・文言とexact一致、emphasis参照一致、output1080×1920/30fps、speaker1。

production `load_payload()`と`_json_env()`の**exact AST**を、fake environmentとjson moduleだけで実行してpayload一致を確認した。renderer module全体はimportせず、main/build_video/VOICEVOX/FFmpegは呼ばない。exact pure helpersでscene segmentation、caption emphasis/ASS escape、音声24秒と仮定したcaption timing fitを検証。実音声時間が18秒を超えるとcurrent rendererはcaption時刻をscaleするため、最終字幕時刻を実測済みとは主張しない。

BGMsfxasset、image/video download、arbitrary file/path、外部URL fetchは不要。実VOICEVOX音声・字体・runtime imageの利用条件やMP4品質は今回未実行/未承認であり、fixture入力だけからlicense/品質PASSを推測しない。

| 境界 | 結果 | 証拠scope |
|---|---|---|
| manual fixture → normalized contract | PASS | UTF-8/strict validation/canonicalization/hashes、provider metadataなし |
| normalized contract → checkpoint | PASS | temporary SQLite manual reference、STARTED→COMPLETED/full read-back/immutable/hash |
| checkpoint → render payload | PASS | SHA検証後adapter、全content field/時刻/字幕参照/JSON値exact |
| render payload → production input loader | PASS | 現production exact function ASTに9 inputsを渡し8 content fields完全一致 |
| current generalized remote schemaでmanual import | 未実装・未承認 | v2候補にはmanual/null-provider pathなし。架空のprovider/effect記録をしない |
| 実MP4を1回実行できる準備済み状態 | **NO** | 入力は互換だがsandbox実行経路/checkout pin/runtimeとspeaker利用条件の準備は次gate。production Pipelineを呼ばない |

このNOはfixture contract failureではなく、現在の許可scopeと実行準備の境界。cross-repo workflow_callのcallee checkoutはcaller repoを取得するため、単にproduction render-shortをusesするだけでproduction renderer sourceが配置されると仮定しない。次gateで既存renderer/workflowの固定codeを再利用する配置とcode/hash pin、$0 runner/artifact予算、voice利用条件を確認する。rendererの重複実装・production変更はしない。

## Offline CIと停止状態

新testsはPython76件＋Node5件（計81件）。既存1,464件のGitHub CI suiteを保持し追加。GitHub CI実件数・run IDは今回の別audit-evidence receiptで確定する。全testsはtrusted native guard / no sockets / no exec / no media writes下で実行する。拒否probeの成功は外部通信/実行ではない。

malformed JSON、missing narration、empty scenes、invalid timing、oversize、unknown/provider field、bad expected hash、persisted hash mismatch、external asset/path、immutable completion、request driftを拒否。修正・再生成・retryを伴わない。

credential作成/登録、AI API/inference、D1 remote read/write/migration、Worker deploy/invocation、実render、YouTube/SNS、external provider通信すべて0。TEST_ONLY/DRY_RUN/NO_PUBLISH/EMERGENCY_STOP=true。live_ready=false / posting_permitted=false。provider primary/fallback未選定、eligibility auditはBLOCKEDを維持。

今回追加のmanual render workflowはplaceholderで `if: false`、allow=false / execution_approved=false、credential参照なし、renderer処理なし。migration/v3 workflowもdisabledを維持し最終headでread-backする。provider-neutral候補と固定旧plan/receiptは変更しない。

次の本人操作は **「固定fixtureを使った実renderを1回だけ準備するか」** の1つ。これは準備の次gateであり、実renderの実行承認ではない。
