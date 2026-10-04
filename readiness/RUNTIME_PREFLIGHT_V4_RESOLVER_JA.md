# 004 resolver-only offline preparation

Parent: `2654474464df30781a5b5ddfaaa0b1eb00af4655`。
003は`BLOCKED_PACKAGE_DEPENDENCY_CLOSURE`のまま。003 plan・index evidence・workflowはbyte単位で変更しない。
001/002 marker/runを保持し、rerun/retry/resumeしない。003/004/render markerは未作成。
004 identity: `manual-fixture-runtime-preflight-20261005-004`。
marker候補: `audit-evidence/consumed/manual-fixture-runtime-preflight-20261005-004.json`。

## Prepared scope versus runtime result

今回のPASSはresolver-only code/parser/schema/fake testsのoffline準備だけ。
実runner inventory、実transaction、実fingerprintはまだない。
実行結果のinstall_countは「提案数」であり実install数ではない。
Activation preparationではworkflow jobをrepository/event/branch限定conditionへ変更。
静的allow/execution_approved envとplan承認フラグは削除。唯一の承認経路はmarker/history guard。
setup/runtime stepはmarker PASS outputs allow=true / execution_approved=trueの両方が必須。
adapter入口でも同じprimary guardを再実行し、receiptのidentity/consumed/allow/approval/no_retry/no_resumeを照合。
markerは未作成であり、今回runtimeの実行承認はない。
その後のlaunchはそのapproved parentのsingle-parent、004 marker Added1件のみ。
permissionはcontents/actions read、writeなし。workflow_dispatchなし。
既存marker guardでmarker/history/diff/parent/attempt1を検証し、adapter入口でも再確認。
marker成立を永久consumption pointとする。setup/timeout/parser failureでも再利用しない。

## Fixed source/index

003のroot10 exact version/filename/SHA256/InRelease/index/keyring evidenceをそのまま参照。
sourceは`https://archive.ubuntu.com/ubuntu`、Noble release、main/universe、amd64のみ。
security/updates/ESM/Pro/PPA/third-party/snapは混ぜない。release snapshotを現在のsecurity stateとは主張しない。
004は公式metadata GETのみ（InRelease、公式archive keyring、main/universe Packages.xz）。
.deb GETをURL whitelistで拒否。redirect拒否、各GET1回、retry0。
InRelease/keyring SHA256は既存証拠とexact照合。gpgv VALIDSIG fingerprint一致必須。
compressed index SHA256/sizeをInReleaseおよび003 evidenceと照合。root control record filename/hashも照合。
indexが変わっていればSTOP。apt-get updateは実行せず、検証済みindexからprivate listsを構築する。
これはaptのglobal index更新でもpackage downloadでもない。

## Dedicated resolver configuration

新しい`$RUNNER_TEMP/plm-resolver-004-*`だけに専用sources.list/config/lists/cache/status snapshotを作る。
APT_CONFIGでhost apt.conf.d、sources.list.d、preferences、trusted key fragmentsを読まない。
host hookを継承せず、dpkg pathは`/bin/false`。root/sudoを使わない。
子process環境はPATH/LC_ALL/LANG/HOMEと専用APT_CONFIGのみ。GH_TOKEN等は渡さない。
subprocessは固定gpgvと固定apt-get --simulateだけ。shellなし。
command whitelistはexact root10のsorted `package=version`を含む固定argvとの一致を要求。
--simulate / --no-download / --no-install-recommends。installというAPT subcommandをsimulationで使うがinstallは行わない。
宿主`/var/lib/dpkg/status`をread/hashし、readonly private copyをresolver入力にする。
half-installed/foreign architecture等はSTOP。simulation後にhost status同一bytesを再確認。

## Parser and PASS gates

LC_ALL=C、stdout 2,000,000 bytes / stderr 65,536 bytes / 120秒を読み取り中に制限し、outputをmemoryだけに保持。上限/timeout時はprocess groupを停止。raw stdout/stderr/bodyは保存・出力しない。
Inst/Conf/RemvとAPT totalsを厳密照合。未知format、重複、欠落、origin/arch不一致はSTOP。
Inst旧versionを実inventoryと照合。Debian epoch/upstream/revision比較でInstall/Upgrade/Downgradeを分類。
Remove/Downgradeは即STOP。すべてのUpgradeも自動PASSなし。
完全列挙できたUpgradeはstructured packageごとの旧/新version、source/pocket、review理由を出す。
root10はexact。全変更packageとrootのDepends/Pre-Depends closureを実final inventoryで検証。
Keepはこのselected closureに必要な既存packageだけ。無関係なhost packageはinventory hashでbind。
Keepを含む全selected packageのexact version/amd64-or-allを同じ検証済みofficial indexに照合。
現在runnerのsecurity/update版がrelease indexにない場合、無理にrelease版へ降格せずsource mismatchでSTOP。
virtual/alternativeはProvidesとversion constraintを照合し、唯一のselected providerを記録。
複数の適格provider/alternativeが残れば推測せずAMBIGUOUS。選択0はUNRESOLVED。
最大1000 package、cyclesはvisitedで有限。未解釈dependency grammarもSTOP。

## Canonical transaction and 005 boundary

`apt-transaction-v4.schema.json`がcanonical transaction構造を定義。
package name順、exact version、architecture、action、repository/suite/pocket、filename/hash、
dependency/provider selections、inventory hash、signed index cohort hashを含める。
JSONはsort_keys=true、separators=(',',':')、ensure_ascii=true、NaN禁止でcanonical bytes化。
SHA256がtransaction_fingerprint。Install/Upgrade/Remove/Downgrade/Keepの提案数も含む。
004 PASSはremove=0、downgrade=0、upgrade=0、未解決/曖昧/unknown source=0の場合だけ。
PASS時のみproof_kind=SIGNED_SOLVER_TRANSACTION_PROOFとvalidated canonical JSON/fingerprintをjob log/summaryへ出す。BLOCKED時はsafe code/counts/upgrade reasonsのみとしcanonical/fingerprintは出さない。artifact/cache uploadは0。

005は別identityと別承認。ここでは005 workflow/marker/installerを作らない。
後続はGitHubから004の固定run ID/attempt1/launch SHA/markerと原canonical reportをread-onlyで取得し、
承認されたfingerprint/report hashと照合。貼り付け・手動編集済みJSONをsource of truthにしない。
005 runner inventory/indexが一致し、再simulation transactionも同fingerprintの場合だけinstall候補にできる。
005でrunner/image/apt状態が変わればSTOPし、004の結果を都合よく編集しない。
verify_handoffはpureなhash/boundary検証であり、authentic run取得やinstall権限を代替しない。

## Safe diagnostics

固定stageを実行前にflushしjob log/summaryへ記録。return codeは限定整数のみ。
RUNTIME_APT_SOURCE_FAILED / SIGNATURE_FAILED / INDEX_FAILED / SIMULATION_FAILED /
REMOVE_PROPOSED / DOWNGRADE_PROPOSED / UNEXPECTED_UPGRADE / VIRTUAL_UNRESOLVED /
ALTERNATIVE_AMBIGUOUS / TRANSACTION_INCOMPLETE / TRANSACTION_SOURCE_MISMATCH。
すべてRUNTIME_APT_ prefix。未知exceptionもsafe fixed codeに変換。raw exception文字列は出さない。
stdoutを取得できないsimulation失敗はgeneric command codeではなくSIMULATION_FAILED。

## Offline evidence and $0 boundary

fake transaction testsはUbuntu runtime evidenceではない。native no-exec/no-socket guardで検証。
今回apt update/simulation/download/install、package modification、Docker、VOICEVOX、FFmpeg、synthesis、
audio_query、encode、MP4、artifact、D1/Worker/AI/YouTube/SNS、user PCはすべて0。
将来もGitHub-hosted standard ubuntu-24.04だけ。有料runner/card/budget変更なし。
actual render markerは別最終承認まで作成しない。

Official references:
- https://manpages.ubuntu.com/manpages/noble/man8/apt-get.8.html
- https://manpages.ubuntu.com/manpages/noble/man5/apt.conf.5.html
- https://manpages.ubuntu.com/manpages/noble/man5/sources.list.5.html
