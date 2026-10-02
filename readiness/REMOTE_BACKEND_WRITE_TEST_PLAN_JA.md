# 将来のremote backend実書き込み試験：設計のみ

今回実行禁止。migration承認は消費済みで流用不可。新Write Tokenを今回は要求しない。remote write試験の別本人承認と短期資格が必要。

## 最小試験範囲

既存canonical test_jobsにfixture専用platform=test/account_id=test_reference_001/job_id=test-remote-cas-audit-001を1行だけ追加する案。現Workerのlifetime cap=1と競合するため、この行は将来TEST_ONLY同一jobの継続対象として予約する。別job生成や追加行を自動作成しない。fixture fingerprintは固定SHAで、テーマ/動画/Token/個人データなし。既存行があれば再INSERTを実行せず手動照合。

1. Readで最新all-D1 inventory=1、schema・空行・bookmark・Free・Account/DB照合。
2. INSERT ON CONFLICT DO NOTHING 1回、SELECTでexact fingerprint/claimant/version=1を確認。
3. 同じidentity・異なるfingerprintのINSERT conflict 1回。row数1・元fingerprint不変をReadで確認。ただし不変性は「この操作パス」のみで、DB自体のUPDATE禁止は未実装。
4. 独立runner 2個から同じversion=1/state=readyにconditional UPDATEを各1回。勝者changes=1が1個、敗者changes=0が1個、version=2、state=dispatchingを期待。GitHub/SNS dispatchは行わない。
5. stale claimant/version=1のconditional UPDATEを1回。changes=0と元fingerprint不変を期待。
6. processを終了し、別runnerのSELECTで同じrow/versionを確認。古い外部dispatchを再現/再送しない。
7. exact winning claimant/version=2/state=dispatchingからstate=unknown/version=3にconditional UPDATEを1回。unknownを終端保存、再送/再claimしない。

上限：mutation SQL送信6回、成功row mutation最大3回（INSERT、winner CAS、unknown保存）、test row最大1、read API最大20、全API最大30。条件不成立で減らすことは可、増やすことは不可。並行runnerは2個。別途remote試験承認文にfixed SQL/params SHA・各request receiptを固定する。readonly SQLは送信前allowlist検査。全段階を順序receiptで記録し、run_attempt=1限定。各SQL送信前にattempt消費・各runId/stepId照合し、timeout/unknownで予定残りを中断、盲目的再送をしない。

SQLite referenceのCASとD1のbatch/transaction仕様の一般説明だけでは実D1の競合試験PASSにしない。affected rowsの返却、実runner独立性、DBのRead readback、restart後の一致が必要。schemaにowner_epoch/fencing_token/checkpoint/replay ledgerがないため、この6回でfull fencing/checkpoint/replay契約を証明しない。その実装/schema拡張は別レビュー・別非破壊migration承認が必要で、0001を再実行しない。

## Tokenとrollback

短期account-owned Token、固定AccountのD1 Writeのみ（Account内全D1に届くため最新all inventory=対象1件が必須）。Workers/Admin/Billing/Token管理なし。今回使用しない。予定Secret PLM_CF_D1_BACKEND_TEST_TOKEN。本人がscopeと最短TTLを確認し、試験結果の成功/失敗/timeout/unknown全てで直後にCloudflare失効→確認→GitHub Secret削除。scope API検証不可ならowner evidenceとAPI未検証を明記。

削除不要：1行を隔離されたtest identityの監査証跡として残す。expected state=unknown、再送禁止を保ち、新jobの余地を作るためDELETEしない。rollbackはremote処理停止・資格失効・read-only手動照合。Time TravelはDB全体を戻すため既存証拠を失い得る。復元/DELETE/DROPは別の本人承認対象で、自動rollbackにしない。

CAS送信結果不明の場合は「0成功」と推測しない。手動Read照合までremote atomicity gateはUNVERIFIEDまたはBLOCKED。外部副作用は一切送信しないので、これはlive job往復の承認にはならない。
