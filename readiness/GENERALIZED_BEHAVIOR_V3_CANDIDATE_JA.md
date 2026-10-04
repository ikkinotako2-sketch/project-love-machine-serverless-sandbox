# V3 candidate: remote success/CAS + exact-SQL offline invariants

旧run37167246069 / 37169509729とidentity001/002は永久consumed。ACTIVE job2行を保持。resume/retry/resend/DELETE/reset禁止。V2 Token cleanupは本人確認の別receiptへ保存、旧receiptは変更しない。

新identity: rt-behavior-20261004-003 / youtube_synthetic_rt_003。candidate段階ではremote rowを作らない。Write Token未要求、実test未承認、execution runner未作成。

固定plan raw SHA256: 080d6aacc968cfc1de5b6061037e9b6bc23e5fac78535b7e3d0d4c50bd87134d
固定offline oracle raw SHA256: 33cceab6d611fda4e80df624c0947c94dbc33f7d571b8811e2b725f56372074b

33steps / mutation sends最大33 / successful logical changes最大18 / runner1。16 APPLIED +17 NO_OP。job/script/render各1、GENERATION/RENDER/UPLOAD各1、callback1、新規最終7rows。最終global counts: job3（既存ACTIVE2＋新SUCCEEDED1）、script1/render1/effect3/callback1。全SQL/paramsと全before/after/final rowsは固定planに収録。old2rowは全stepでexact保持。

## 検証分離

| 内容 | remote候補 | exact migrated SQL offline oracle |
|---|---|---|
| identity/immutable conflict | predicateで0 change | guard ABORT token＋全5table不変 |
| owner handoff/CAS | 正常handoff1、stale owner/fence0 | script/effect存在後のhandoff ABORT |
| script/effect/render lifecycle | STARTED→COMPLETED JSON/SHA、各effect正常transition、artifact/ref/quality PASS | 未完script render拒否、script/render/effect immutable ABORT |
| UNKNOWN中の再送/再予約 | state/NOT EXISTS predicateで0 change | no-resend/precondition ABORT |
| callback stale/duplicate/conflict | epoch/fence guard0、exact duplicate0、conflict guarded0 | identity/payload conflict ABORT、callback immutable ABORT |
| callback atomic completion | callback INSERTでlogical changes3＋full readback | exact callback_apply SQLとconstraintsもfixture使用 |

remote 0 changeはclient SQL guardの証拠であり、DB triggerがremoteで拒否した証拠ではない。unique index / trigger / immutable invariantはfresh read-only schema＋raw SQL hashと、そのexact SQLのoffline SQLite fixtureを組み合わせる。local SQLiteとremote D1の完全な実行同等性は主張しない。

intentional ABORTはremote suiteに0件。拒否message decoderを呼ばず、HTTP200 / success=true / errors=[] / served_by_primary=true / exact meta.changes / full readbackが唯一の成功条件。7500を含むerrorはwrapperを問わずSTOP。通常の全step一致にCloudflare wrapperは不要。ただし予期しないerror/timeout/readback mismatchなら停止する。

offline oracle17件はremote mutation用ではない。captured migrated table5＋trigger11のSQLそのものからfixtureを作り、expected ABORT token / SQLite extended code1811 / 全5table before-after exactを検証。SQL hashを各objectについて固定。原文error wrapper / provider body / token / headersを保存しない。

retry/resend/fallback/delete/drop/reset/automatic rollback0。unknown→次mutation0・read-only reconciliation最大1set。Worker/AI/render execution/YouTube/SNS/external provider0、live_ready=false / posting_permitted=false /4安全フラグtrue。execution workflow hard-disabled / allow=false / UNAPPROVED。

次の本人操作は1つ: 「このv3固定planで、Write Tokenを使わないfresh read-only preflightを進めてください」と依頼する。Token発行依頼・登録・最終実test承認は別段階。今回新Write Tokenを要求しない。

production / sandbox main / n8n / V1 /既存YouTube Pipeline / PR15/16変更なし。
