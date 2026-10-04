# AI provider eligibility / $0 durability audit — 2026-10-04

**BLOCKED_NO_COMPLIANT_ZERO_COST_PROVIDER**。今回の公式公開情報と本人evidenceで全必須条件を証明できたproviderは0。世界中に適格なサービスが存在しないという結論ではない。primary / fallbackは未選定、credential要求なし。

対象はsandbox readiness branch `plm-offline-readiness-v1-20261002`だけ。公開一次情報の閲覧とoffline fixture検証のみ。credential作成/登録、provider API、D1 mutation/read、Worker deploy/invocation、AI inference、render、YouTube/SNSすべて0。公開資料の検索・閲覧は推論API通信ではない。

V3 33/33 SUCCESSは保存済みreceipt `37173135193`に基づく。Token/Secret cleanupは本人報告として別receiptに保存し、独立verify済みとは主張しない。v1/v2/v3 identityとrunは永久consumed、証拠rowの移動・コピー・削除・上書きなし。Read Token維持。

## 判定境界

Gemini禁止の本人指示を尊重し、正確な本人年齢が未収集のまま18歳以上条件を満たすと仮定しない。正確な年齢・13歳以上の証明・保護者同意は未収集で、仮定してPASSにしない。Cloudflare account保有は契約適格性の証明にしない。数値年齢が書かれていない規約を「18歳以上」と読み替えない。法域・契約能力・適切な同意の条件を確認できるまで保留。

必要条件は継続$0、有料契約なし、支払方法登録なし、本人の適格性、headless server inference、1日6 generation、日本語台本、検証可能JSON。無料trial・初回credit・期限限定特典は不可。月次で更新する無料creditはtrialと区別する。公開quotaは理論容量であり、本人accountの割当やモデル日本語品質を実測した証拠ではない。

| 近い候補 | 継続無料の公開情報 | FULL PASSを妨げる点 |
|---|---|---|
| Cloudflare Workers AI | 10,000 Neurons/day、00:00 UTC reset、カード不要と製品資料に記載 | Self-Serve / Developer Platform規約で本人の契約適格性を独立証明できない。数値最低年齢/未成年同意経路を公開資料から確定できない |
| Mistral API Free | カードなしでAPI有効、monthly allowanceあり | 13歳以上＋未成年の保護者許可の本人evidenceなし。具体的RPS/TPM/月quotaはOrganization Limitsに依存。Freeは評価/prototyping向けで継続production用途の適合も未確定 |
| Hugging Face routed inference | 月$0.10 recurring credit、providerの別account不要 | 13歳以上＋法的契約能力、downstream条件、固定model/providerのJSON対応・実効rate limitを未証明 |

Groq / OpenRouter / Ollama Cloud / PublicAI.coは18歳以上。Cohereは居住法域の成年・契約能力が必要で、free evaluationとproductionは別。OpenAI APIに継続無料枠なし。Cerebrasは支払方法検証後$5・30日期限のtrialのみ。Pollinationsは現行公式規約本文を取得できず、無条件で更新する無料allocationも未確認。Geminiは本人指示で禁止、GitHub Modelsは2026-07-30退役済み。

## $0容量の比較（API未使用、計算のみ）

- Cloudflare Qwen3-30b-a3b-fp8: 入力4625 / 出力30475 Neurons per million tokens。入力2048＋出力4096を1日6回と仮定すると **805.7856 Neurons/day**。容量は足りる計算だが契約適格性を代替しない。
- Hugging Face catalogのQwen3-4B-Instruct-2507:nscale: 入力$0.01 / 出力$0.03 per million tokens。同条件を31日（186回）で **$0.02666496/month**。月$0.10を一律「6回/日には不足」としない。モデル/provider pairingのstructured outputや本人のrate limitsは別の未確認gate。
- Mistralは公開資料だけで本人Organizationの数値quotaを固定できない。

この予算は**6件の独立generation、各1 attempt**。旧Gemini fixtureの「2件×最大3 attempts」は継承しない。自動retry / regeneration / fallback=0。価格・quota・ToS・model availability drift時はSTOPし、有料upgradeやmodel自動切替をしない。無料枠・モデルの将来存続保証は全候補にない。

## Provider-neutral backendの最小非破壊候補

現在の `plm_rt_v1_script` は `provider='gemini'` CHECK。provider / model / request SHAをscript guardがimmutableにする。v1 render/effect triggerはv1 script tableを直接参照する。script tableだけ追加しても閉じたworkflowには接続できず、既存trigger変更またはproviderの虚偽記録が必要になる。

したがって既存graphを一切変更しない最小の閉じた候補として、**新namespace `plm_rt_v2_` に5 tables / 11 triggers / 14 autoindexes**を追加する。新scriptのproviderは小文字ASCII識別子2〜32文字、先頭英字。model/request/provider immutability、checkpoint-before-render、effect/callback atomicityは継承。識別子CHECKは適格providerの認可ではなく、別のeligibility gateを必須とする。primary未選定なので実adapterもexecutorも作らない。

columns: callback=10 / effect=13 / job=13 / render=11 / script=14、新row=0。既存v1全9 rows（旧ACTIVE2を含む）、stage2成功3 row、atomicity、test_jobs、既存schema/indexes/triggerはそのまま。`_cf_KV`はschemaだけ確認しcontentは `NOT_APPLICABLE_RESERVED_UNQUERYABLE`。

before/afterはV3 SUCCESS receiptの参照snapshotとoffline SQLite candidate結果であり、今回fresh remote D1監査をした証拠ではない。将来migration承認の前にはRead Tokenでfresh schema/inventory/protected rows/bookmarkとcandidate不存在を再取得しなければならない。

migration route候補は `/import` SQL-fileのinit→upload→ingest→status poll。execution/runner各1、side-effect最大3、poll最大3、合計HTTP最大6、`/query` mutation=0。init自体がcached fileを適用し得るため、timeout/unknown/unexpectedなら次side-effect送信前にSTOP。read-only reconciliation最大1セット、resume/retry/resend/fallback/自動rollbackなし。PARTIAL_APPLIED / NOT_APPLIED / STILL_UNKNOWNは保存して停止し、DROP/restoreによるrollbackは行わない。

この候補は**NOT APPROVED / remote application=0**。workflowは `if: false`、allow=false、execution_approved=false、4安全フラグtrue。migration credentialを参照するコード・runnerはない。

### 固定raw SHA256

| File | raw SHA256 |
|---|---|
| `serverless/migrations/0008_provider_neutral_roundtrip_backend.sql` | `7734fe9ae6d950b5af444cc9a3f917b3da8d050c5e63083f51a79ea42d620bfe` |
| `serverless/provider-neutral-backend-after.json` | `d0de3cd14ac3aa1afb55a358635c5a32a9c0f90528d1ca42f84ab4beb6fd54c3` |
| `serverless/provider-neutral-backend-before.json` | `02d8d6c9e0d131dfbfc4088af072ca704589f31e3753a59a80a10cd71b2e31b9` |
| `serverless/provider-neutral-backend-plan.json` | `277fcf6ae8f465ae574e4c5f903b8c506689baf632a0e1e2d68ed2bd7dd5820a` |

## generation contractとdurability

既存 `readiness/generation_contract.py` のGemini request/response fixtureは過去offline compatibility証拠として保持する。実credential作成・使用やprovider接続の認可には使わない。新 `provider_neutral_generation.py` はdata-onlyで、SDK/HTTP/credentialを持たない。eligible evidenceがすべてexact trueでない限りrequestを認可しない。Gemini/GitHub Modelsは常に禁止。

将来の固定経路は **eligible providerの1回のtext generation → strict JSON/local schema検証 → validated script JSON＋SHAをdurable script checkpointへCAS保存 → 保存済みcheckpointだけをrender入力へ変換 → 既存render-short.ymlを再利用 → artifact ref/SHA＋quality PASSをdurable保存 → UPLOAD reservation/SENT → private固定・notifySubscribers=falseの既存YouTube adapter → exact-once callbackでeffect CONFIRMEDとjob SUCCEEDEDをatomicに成立**。既存production Pipeline/adapter/workflowは変更していない。script validation前・durable保存前のrenderは不可。

timeout / ambiguousはUNKNOWNとしてSTOPし、再生成・再render・再upload・再送・provider fallbackをしない。responseの途中終了、invalid JSON、quota/model drift、hash/identity mismatchもSTOP。JSONはduplicate keys、NaN/Infinity/overflow、oversize/depth/control chars、schema逸脱を拒否。保存済みJSONはreload時に再validationしSHA/identityを再確認する。raw provider bodyやcredentialを永続化しない。

## Offline証拠

候補exact SQLをSQLiteで適用し、before/after schema、columns、autoindexes、新row=0、全旧証拠row不変を確認。独立offline identityの33-step graphで16 APPLIED / 17 no-op / logical18 / final7 rowsを再現し、callbackのatomic changes=3を含め全before/after snapshotを照合。候補namespaceの17 negative oracleは期待ABORT tokenと全row不変を照合。既存remote exact-migrated v1 SQL用17 oracleと証拠を混同しない。

remoteのchanges=0はclient predicate no-opの証拠でありDB trigger拒否の証拠ではない。今回remote behavior testは実行していない。公開provider資料の調査結果とSQLite成功は、本人のAPI eligibilityやactual inference成功の証拠ではない。

CI結果は別のaudit-evidence receiptへ保存。live_ready=false / posting_permitted=false、TEST_ONLY/DRY_RUN/NO_PUBLISH/EMERGENCY_STOP=trueを維持する。

## 規約を回避しない$0の次の選択肢

1. **AIを使わない、人が用意した日本語台本JSON fixtureでoffline接続監査を継続する。** 新しいaccountやcredentialは不要。
2. 実AIを再検討する場合は、適正な本人年齢・保護者同意・契約適格性を確認できるサービスだけを扱い、Mistral/HFの公式quotaと使用条件を追加確認する。本人accountのみ、年齢詐称・別人account利用・条件回避は不可。この監査では登録を求めない。
3. 本人が対象サービスの利用条件を満たすまでAI工程を停止する。支払方法・有料plan・trial依存に切り替えない。

次の本人操作は **「AIなしの台本JSON fixtureでoffline接続監査を続けるかを選ぶ」** の1つ。credential作成・登録・migration承認は今回求めない。

## 候補別の公式一次情報

以下は2026-10-04の公開資料だけ。取得できない/数値非公開の項目は未証明として除外。最大contextと最大outputを同一視しない。model名は調査例であり、使用対象の固定・provider認可ではない。

### gemini — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 18 |
| 未成年・契約条件 | 18歳未満に向けた/利用されるAPI Clientsも制限。本人指示でcredential作成/使用禁止。 |
| API/automation/headless | 禁止 |
| 継続無料枠 | 調査候補から明示除外 |
| カード/支払方法 | NOT_AUDITED_AFTER_OWNER_EXCLUSION |
| quota | NOT_APPLICABLE |
| reset | NOT_APPLICABLE |
| 公開model例 | 使用対象未選定 |
| JSON/strict | NOT_APPLICABLE |
| 最大出力 | NOT_APPLICABLE |
| authentication | 禁止 |
| 商用/自動SNS制約 | 禁止 |
| data条件 | 既存fixtureは実AI responseではない |
| 廃止/変動risk | 候補にしない |

公式根拠: [gemini_terms](https://ai.google.dev/gemini-api/terms)。

### github_models — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | NOT_APPLICABLE_RETIRED_API |
| 未成年・契約条件 | GitHub account条件とモデルAPI availabilityは別 |
| API/automation/headless | inference API退役 |
| 継続無料枠 | RETIRED |
| カード/支払方法 | NOT_APPLICABLE |
| quota | 0 |
| reset | NONE |
| 公開model例 | 使用対象未選定 |
| JSON/strict | NOT_APPLICABLE |
| 最大出力 | NOT_APPLICABLE |
| authentication | 既存GitHub tokenをinferenceへ転用しない |
| 商用/自動SNS制約 | NOT_AVAILABLE |
| data条件 | NOT_APPLICABLE |
| 廃止/変動risk | 2026-07-30退役済み |

公式根拠: [github_retired](https://github.blog/changelog/2026-07-30-github-models-is-now-retired/)。

### groq — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 18 |
| 未成年・契約条件 | 18歳未満はCloud Services access/use禁止。保護者代理credential案なし。 |
| API/automation/headless | 文書化API integration許可。将来headless HTTP可能、SDK retryは使わない |
| 継続無料枠 | Free plan usage-based limits |
| カード/支払方法 | 公式資料からカード不要を独立確定できず。年齢hard fail後に登録画面を開かない |
| quota | gpt-oss-20b/120b:30 RPM,1000 RPD,8000 TPM,200000 TPD |
| reset | RPD/TPM reset headerで相対reset。固定daily timezoneはこの資料で確定しない |
| 公開model例 | openai/gpt-oss-20b, openai/gpt-oss-120b, qwen/qwen3.8-27b |
| JSON/strict | 上記3モデルはjson_schema strict:true対応 |
| 最大出力 | gpt-oss20b/120b max completion65536、Qwen3.8 max16384。Free throughput limitsは別 |
| authentication | Bearer API key |
| 商用/自動SNS制約 | service/model AUP・権利・非欺瞞を要確認。今回年齢で除外 |
| data条件 | 推論contentは通常保持しない、信頼性/abuse時最大30日。usage metadata保持 |
| 廃止/変動risk | Previewは短期廃止可。古いLlama無料枠情報は使わない |

公式根拠: [groq_terms](https://console.groq.com/docs/legal/services-agreement), [groq_limits](https://console.groq.com/docs/rate-limits), [groq_models](https://console.groq.com/docs/models), [groq_json](https://console.groq.com/docs/structured-outputs), [groq_data](https://console.groq.com/docs/your-data)。

### cloudflare_workers_ai — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 公開数値未確認・適格性未証明 |
| 未成年・契約条件 | 現行SSA/Developer Platformに明示的数値年齢や未成年同意の承認経路を確認できない。契約成立・本人の契約能力/適格性を未証明。Website TermsはSSA製品を適用外とするため別規約の年齢を流用しない。既存accountは証明ではない。 |
| API/automation/headless | REST AI run endpointでheadless可能。Worker deploy/invocation不要だが今回inference0 |
| 継続無料枠 | Workers Free ongoing allocation; no paid upgrade |
| カード/支払方法 | Freeはカード不要。Paidやfrontier/prepaid creditは除外 |
| quota | 10000 Neurons/day。Qwen3-30b入力4625/output30475 Neurons/M tokens |
| reset | 00:00 UTC daily |
| 公開model例 | @cf/qwen/qwen3-30b-a3b-fp8 |
| JSON/strict | response_format JSON/schema対応。local validation必須 |
| 最大出力 | max_tokens default2000、absolute output ceilingは公開parameter schemaに明記なし。4096要求の事前保証なし |
| authentication | Account-scoped Bearer API Token, future Workers AI最小scope。D1 Read Token流用不可 |
| 商用/自動SNS制約 | SSA2.7 spam/technical abuse等禁止。Developer terms第三者model terms遵守。正常なAPI automationとquota回避を混同しない |
| data条件 | AI inputs/outputsはCustomer Content、同意なしgenerative model trainingに使わない |
| 廃止/変動risk | SSA8で変更/廃止可。Freeアクセス/paid指定やモデルcatalog driftでSTOP |

公式根拠: [cf_ssa](https://www.cloudflare.com/terms/), [cf_dev](https://www.cloudflare.com/service-specific-terms-developer-platform/), [cf_website](https://www.cloudflare.com/website-terms/), [cf_price](https://developers.cloudflare.com/workers-ai/platform/pricing/), [cf_card](https://www.cloudflare.com/products/workers-ai/), [cf_model](https://developers.cloudflare.com/workers-ai/models/qwen3-30b-a3b-fp8/), [cf_json](https://developers.cloudflare.com/workers-ai/features/json-mode/), [cf_data](https://developers.cloudflare.com/workers-ai/platform/data-usage/), [japan_majority](https://www.moj.go.jp/MINJI/minji07_00238.html)。

### mistral — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 13 |
| 未成年・契約条件 | 未成年本人のaccount/API利用には適法な保護者/法定代理人同意。本人の13歳以上/同意evidenceなし。Commercial terms2.2(c)も確認。 |
| API/automation/headless | Free mode/PayGo Studio API keyでautomation可。Vibe Code CLI plan keyはautomation不適合 |
| 継続無料枠 | Free mode recurring monthly usage, trial creditと同一視しない |
| カード/支払方法 | False |
| quota | numeric RPS/TPM/month allowanceは本人OrganizationのLimits pageに依存。公開資料のみで6/day確定不能 |
| reset | monthly usageあり。Freeの正確reset時刻/日付は公開資料で確定不能 |
| 公開model例 | mistral-small-latest, Mistral Small 4, Mistral Large 3 |
| JSON/strict | JSON object/custom JSON schema。ローカルstrict JSON必須 |
| 最大出力 | model context:Small4/Large3 256k input+output。absolute output上限は別、固定pinなしでは未確定 |
| authentication | Bearer API key; expiry設定可。Vibe plan keyをAPIへ流用しない |
| 商用/自動SNS制約 | Commercial API契約/usage policy遵守。Freeはevaluation/prototyping向けの記載。長期商用SNSへの継続適合は未確定で禁止断定もしない |
| data条件 | Free mode input/output training使用可、opt-out可。ZDRはFreeそのままでは利用不可(PayGo必要) |
| 廃止/変動risk | latest aliasは変動、変更時STOP。model/version固定前にquotaと契約確認 |

公式根拠: [mistral_age](https://help.mistral.ai/en/articles/347631-can-children-use-mistral-products-and-services), [mistral_consumer](https://legal.mistral.ai/terms/row-consumer-terms/), [mistral_commercial](https://legal.mistral.ai/terms/commercial-terms-of-service/), [mistral_key](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key), [mistral_limits](https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them), [mistral_usage](https://docs.mistral.ai/admin/billing-usage/usage-limits), [mistral_models](https://docs.mistral.ai/models), [mistral_chat](https://docs.mistral.ai/api/endpoint/chat), [mistral_json](https://docs.mistral.ai/studio/conversations/structured-output/custom), [mistral_data](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-intelligence-models), [mistral_zdr](https://help.mistral.ai/en/articles/347612-can-i-activate-zero-data-retention-zdr), [mistral_aup](https://legal.mistral.ai/terms/usage-policy/)。

### huggingface_routed — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 13 |
| 未成年・契約条件 | 13歳以上account条件に加えTerms Execution条項のlegal right/capacity。本人適格性evidenceと下流サービス条件の適合未証明。HF経由を18歳条件回避に使わない。 |
| API/automation/headless | REST/routerまたはInferenceClientでheadless可能。auto provider routing/SDK retriesは将来禁止 |
| 継続無料枠 | Free user monthly credit; one-time trialではない |
| カード/支払方法 | False |
| quota | $0.10/month subject to change。公式catalog Qwen3-4B-Instruct-2507:nscale input $0.01/M output $0.03/M |
| reset | monthly。正確cycle/timeは公開pricingで確定しない |
| 公開model例 | Qwen/Qwen3-4B-Instruct-2507:nscale |
| JSON/strict | json_schema provider/modelごと対応。candidate pairでstrictのexact capability未固定 |
| 最大出力 | Qwen card/context262144は最大outputではない。absolute output/provider throughput未確定 |
| authentication | HF User Access Token(inference permission); routedなら下流provider account不要。Custom Provider Key無料credit対象外 |
| 商用/自動SNS制約 | HF terms/model Apache2.0・下流条件確認必須。未確認の下流年齢条件をHF accountだけでPASSにしない |
| data条件 | HFはrouting body/responseを保存・training利用しない、debug logs最大30日content/tokenなし。下流data policyは別で未固定 |
| 廃止/変動risk | credit価格/額subject to change、model/provider消滅可。固定nscale以外へ自動fallback禁止 |

公式根拠: [hf_terms](https://huggingface.co/terms-of-service), [hf_price](https://huggingface.co/docs/inference-providers/pricing), [hf_models](https://huggingface.co/inference/models), [hf_qwen](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), [hf_json](https://huggingface.co/docs/inference-providers/guides/structured-output), [hf_security](https://huggingface.co/docs/inference-providers/security), [hf_nscale](https://huggingface.co/docs/inference-providers/providers/nscale)。

### openrouter — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 18 |
| 未成年・契約条件 | 2026-08-31現行規約2。古い13歳+guardian条件を使わない。 |
| API/automation/headless | API自体はheadless可。ただし公式routingはupstream errorでautomatic retries/fallbackがあり本方針と不適合 |
| 継続無料枠 | free variantsは存在するが適格性hard fail |
| カード/支払方法 | free variant以外の課金禁止。card要否は年齢除外後未確定 |
| quota | 公開limitsの無料table数値が取得textでは欠落。旧50/day/20RPM値を現行証明にしない |
| reset | free usage counter UTC day |
| 公開model例 | dynamic :free catalog; no selected model |
| JSON/strict | model/provider dependent json_schema;未選定 |
| 最大出力 | per-model。not fixed |
| authentication | Bearer API key |
| 商用/自動SNS制約 | AUP/model terms、rights、nondeception。年齢で除外 |
| data条件 | content/model trainingとlogging permission per provider/settings。opt-in log商用利用licenseあり |
| 廃止/変動risk | モデル随時追加/削除可。route/fallback drift |

公式根拠: [openrouter_terms](https://openrouter.ai/terms), [openrouter_limits](https://openrouter.ai/docs/api_reference/limits), [openrouter_privacy](https://openrouter.ai/privacy/)。

### cerebras — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 13 |
| 未成年・契約条件 | 国のdigital consent年齢以上。API Third-Party Model Terms別途適用。 |
| API/automation/headless | API文書に沿うautomation許可。カード未登録ならAPI/Playground inactive |
| 継続無料枠 | Free Trialのみ |
| カード/支払方法 | True |
| quota | $5 trial credits expires30days。5RPM,30k uncachedTPM,90k totalTPM,1MTPH/TPDはtrialのrate ceilings |
| reset | renewing no-cost allowanceなし。trial失効後購入必要 |
| 公開model例 | gpt-oss-120b, qwen-3.8-27b |
| JSON/strict | per-model Structured Outputs;無料trialであっても候補除外 |
| 最大出力 | public model-specific ceiling未固定。trial credit ceilingとoutput capは別 |
| authentication | Bearer API key |
| 商用/自動SNS制約 | Model terms、Output人間生成と偽らない、commercial solicitation禁止条項。trial限定で長期SNS候補にしない |
| data条件 | Terms user-content license/third-party policies。具体モデルprivacy未選定 |
| 廃止/変動risk | serviceいつでも変更/停止可。trial30日で必ず継続不可 |

公式根拠: [cerebras_terms](https://www.cerebras.ai/terms-of-service), [cerebras_limits](https://inference-docs.cerebras.ai/support/rate-limits), [cerebras_price](https://www.cerebras.ai/pricing)。

### openai_api — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 公開数値未確認・適格性未証明 |
| 未成年・契約条件 | API Services Agreementで合法な契約能力が必要。未成年End Usersはguardian consent。consumer ChatGPTの年齢/Plus資格をAPI契約に流用しない。 |
| API/automation/headless | API integration/headless可、今回credential0 |
| 継続無料枠 | 継続無料API allocationを確認できず |
| カード/支払方法 | True |
| quota | 通常APIは使用料、prepaid最小$5。ChatGPT PlusはAPI無料枠ではない |
| reset | paid credits/rechargesのみ。FREE_QUOTA_NONE |
| 公開model例 | 使用対象未選定 |
| JSON/strict | 対応モデルにstructured outputsあり。$0失格のためモデル選定しない |
| 最大出力 | per model。NOT_PINNED_AFTER_COST_FAIL |
| authentication | Bearer API key |
| 商用/自動SNS制約 | API application+OpenAI policies遵守。$0で除外 |
| data条件 | Services agreement/個別data設定確認必要。候補除外後data plan選定なし |
| 廃止/変動risk | 価格変更/モデル廃止。prepaidはinstant hard spending cutoffでもない |

公式根拠: [openai_terms](https://openai.com/policies/services-agreement/), [openai_billing](https://help.openai.com/en/articles/8264644-setting-up-and-managing-prepaid-api-billing)。

### cohere — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 居住法域の成年年齢と法的契約能力（規約は一律数値18を規定していない） |
| 未成年・契約条件 | Termsは居住国の成年+binding capacity、日本は18。minor exception未確認。 |
| API/automation/headless | API/headless可。ただしproductionはpaid key |
| 継続無料枠 | evaluation/trial keys only; production paid |
| カード/支払方法 | production payment必要。trialのcard要否は未確認 |
| quota | trial1000 calls/month; Chat20RPM |
| reset | monthly。正確resetcycleは未確認 |
| 公開model例 | Command A, Command A+, Command R7B |
| JSON/strict | supported models JSON/schema。未選定output pinなし |
| 最大出力 | per-model docs;未固定 |
| authentication | Bearer API key |
| 商用/自動SNS制約 | trialをproduction用途へ転用しない。deceptive fake reviews/deepfakes等usage policy禁止 |
| data条件 | contract/model privacy選定なし。今回評価key自体も作らない |
| 廃止/変動risk | new models prod keysでもtrial limitの場合あり |

公式根拠: [cohere_terms](https://cohere.com/terms-of-use), [cohere_limits](https://docs.cohere.com/docs/rate-limits), [cohere_prod](https://docs.cohere.com/docs/going-live), [cohere_models](https://docs.cohere.com/docs/models), [cohere_aup](https://docs.cohere.com/docs/usage-policy/)。

### ollama_cloud — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 18 |
| 未成年・契約条件 | May2026 Terms2で18歳以上。Local open-source licenseとcloud契約は別監査。 |
| API/automation/headless | documented APIでheadless可。今回local/cloud inference両方0 |
| 継続無料枠 | Free starter usage monthly resets |
| カード/支払方法 | Free signup card要否は公式pricingのみで未確定 |
| quota | Free starter amount数値とmodel範囲の固定根拠なし。concurrency1 |
| reset | signup日基準monthly、繰越なし |
| 公開model例 | starter cloud models; exact entitlement未固定 |
| JSON/strict | cloud model-dependent; local structured output機能をcloudの保証へ流用しない |
| 最大出力 | per model;未固定 |
| authentication | Bearer API key cloud direct |
| 商用/自動SNS制約 | ownoutputs/review責任。18歳条件あり |
| data条件 | cloud prompts/responses logged/trainedしないとpricing/terms明記 |
| 廃止/変動risk | monthly free amount未固定。terms/modellist変化 |

公式根拠: [ollama_terms](https://ollama.com/terms), [ollama_price](https://ollama.com/pricing), [ollama_privacy](https://ollama.com/privacy), [ollama_api](https://github.com/ollama/ollama/blob/main/docs/api/introduction.mdx)。

### publicai_co — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 18 |
| 未成年・契約条件 | AI inference utility Terms1.2。publicai.io(別サービス)規約と混同しない。 |
| API/automation/headless | API可、account作成botは禁止。headless inferenceはAPI docsに従う |
| 継続無料枠 | API $2 starter credit; recurring free quotaを確認せず |
| カード/支払方法 | starter後payment条件未確定 |
| quota | new account $2 starter credit; recurring証明なし |
| reset | starter replenishment根拠なし |
| 公開model例 | public gateway catalog;not selected |
| JSON/strict | OpenAI-compatible API;strict pair未固定 |
| 最大出力 | per-model;未固定 |
| authentication | gateway API key/Bearer |
| 商用/自動SNS制約 | Terms1.4 unsafe automation:human oversightなしSNS posting禁止。本目標に不適合 |
| data条件 | research data sharing opt-out、external modelproviderdata terms |
| 廃止/変動risk | research/educationprimary・service/modellist変化 |

公式根拠: [publicai_terms](https://publicai.co/tc), [publicai_docs](https://platform.publicai.co/docs)。

### pollinations — EXCLUDED

| 項目 | 確認結果 |
|---|---|
| 最低年齢 | 公開数値未確認・適格性未証明 |
| 未成年・契約条件 | official enter termsがpublic retrievalで本文0行。age/minor/contract条件証明不能。非公式pollinations-ai.comを根拠にしない。 |
| API/automation/headless | public API headless仕様あり。terms適格性未証明 |
| 継続無料枠 | Pollen/quests案内。現行always-free quotaを確定できず |
| カード/支払方法 | UNVERIFIED |
| quota | Anonymous/Seedの旧rate情報を現行根拠にしない。quest creditは無条件ongoing allocationではない |
| reset | UNVERIFIED |
| 公開model例 | official dynamic catalog includes third-party models;禁止Gemini等は選ばない |
| JSON/strict | chat-completion API、strict schema/current output ceiling未証明 |
| 最大出力 | UNVERIFIED |
| authentication | current API key/OAuth docs;匿名利用条件未確定 |
| 商用/自動SNS制約 | UNVERIFIED |
| data条件 | UNVERIFIED |
| 廃止/変動risk | gateway/model/tier/creditsに変更リスク |

公式根拠: [pollinations_terms](https://enter.pollinations.ai/terms), [pollinations_docs](https://gen.pollinations.ai/docs), [pollinations_dashboard](https://pollinations.ai/dashboard/api-keys)。

