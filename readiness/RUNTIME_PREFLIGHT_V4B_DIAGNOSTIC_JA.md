# 004B resolver diagnostic — offline preparation

基準parent: `8bd100fadea4f857cfa1935283992a09a119b090`。
004 identity/markerは永久consumed。run `37216447727` attempt1は保持しrerun/retry/resume禁止。
004保存証拠はsignature rc0、simulation rc100、RUNTIME_APT_SIMULATION_FAILED。
raw streamsを保存していないので004の原因は特定できない。release-onlyとrunner stateの競合は仮説。
001/002 markerと003 blocked evidenceは保持。003/render markerは未作成。
新identity: `manual-fixture-runtime-preflight-20261005-004b`。
marker候補: `audit-evidence/consumed/manual-fixture-runtime-preflight-20261005-004b.json`。
今回markerは作らない。005 workflow/installerにも進まない。

## Authorization and scope

job conditionは既存repository/push/readiness branch限定、push pathsはexact004b markerのみ。
permissionsはcontents read/actions read。static承認trueはなし。
primary marker/history guardだけがPython setup/diagnostic stepを開く。adapterもguardを再確認。
004 guardはIDENTITY_CONSUMED_004で常にSTOP。新004bは独立したcandidate。
launchは別本人承認のapproved preparation parentからsingle parent、marker Added1件のみ。
launch前にworkflow/plan/fixture/schema hashes/headを再照合。
成立後は永続consumed、失敗/unknown/cancel/timeoutでもsecond launch/rerun/retry/resumeなし。
markerなしの準備pushでruntime workflowはtriggerされない。

## Four named isolated comparisons

すべてUbuntu公式 `https://archive.ubuntu.com/ubuntu` のamd64 main/universeだけ。
1. release_only: noble
2. release_updates: noble + noble-updates
3. release_security: noble + noble-security
4. release_updates_security: noble + noble-updates + noble-security

単独updates/securityは依存baseを欠くため、releaseを共通baseとして明示的に追加比較する。
各構成の専用source list/config/lists/cache/status snapshotをRUNNER_TEMPに分離。
これは固定4-case診断であり、同一caseを再実行するretry/fallbackではない。
root10は各caseで既存exact package=versionを維持。新しいversionを代わりに指定しない。
各case simulationは最大1回、合計最大4回。return code100は分類して次の別source構成の診断へ進む。
署名/hash/source/inventory drift/timeout/出力上限等が失敗したらcandidate全体STOP。
PPA/third-party/Pro/ESM/snap/有料repoは禁止。

## Signed metadata boundary

003のroot evidence bytes/filename/SHA256/InRelease/indexとroot constraintsを変更しない。
nobleは003の固定release indexをexact hash照合。
updates/securityは将来のlaunch時に取得する公式署名済みsnapshotで、現在のversion/SHAを予言・捏造しない。
各InReleaseのUbuntu Origin/Label/Suite/Codenameを照合し、pinned archive keyring SHAと
Ubuntu signing fingerprintによるgpgv VALIDSIGを要求。
対応SHA256 sectionからmain/universe Packages.xz hash/sizeを得てindex照合。
各suiteは別dictionaryで保持し、同versionのsource/pocketを混同しない。
metadata GETはkeyring1 + 3 suites × (InRelease1 + Packages2) = 最大10、redirect/retry0。
apt updateは不要。verified indexからprivate APT listsを作る。
.deb URLはwhitelistに含めず拒否。download/install adapterなし。

実inventoryを1回read/hashし各caseへ同じsnapshotを渡す。毎case後にhost status bytesを再照合。
installed版がreleaseにはなくupdates/securityにあるかをpackage/version/arch単位で比較する。
index absenceだけでhost packageをthird-party由来と断定しない。
coverageは限定sampleと全体countを分けて表示し、dependency closureやtransaction proofとは扱わない。

## Safe fixed diagnostics

- RUNTIME_APT_EXACT_VERSION_UNAVAILABLE
- RUNTIME_APT_DEPENDENCY_UNSATISFIED
- RUNTIME_APT_HELD_CONFLICT
- RUNTIME_APT_DOWNGRADE_REQUIRED
- RUNTIME_APT_BROKEN_PACKAGES
- RUNTIME_APT_SOURCE_INDEX_MISMATCH
- RUNTIME_APT_PACKAGE_NOT_FOUND
- RUNTIME_APT_UNKNOWN_SOLVER_FAILURE

expected version不存在/package不存在は検証済みindexで区別。
APTが不存在と述べた版がindex上に存在する場合はsource/index visibility contradiction。
依存messageはknown package nameのみ。held conflictはactual hold状態とsolver messageの双方を要する。
一般的な"held broken packages"句だけではheld/brokenを断定しない。
brokenはactual dpkg inventory stateから確認。downgradeはinstalled rootがrequestより新しい場合や固定APT message。
複数signalならfixed codeのlistを保ち、単一原因を推測しない。未知patternはunknown。

package name/expected version/installed version/candidate version/source/suite/arch等のstructured metadataだけを出す。
candidate versionはhighest verified index versionでありactual apt policy candidateとは主張しない。
free-form message、URL本文、stderr/stdout、例外文字列、tokenはreportに入れない。
stdout 2,000,000 bytes / stderr 65,536 bytes / 120秒の上限を読み取り中に適用。
raw streamsはmemory内で分類後に破棄。file/log/artifactへ保存しない。子process envにcredentialsなし。
固定stage/case/return codeだけ先にflushし、kill/timeoutでも到達stageが分かる。

## Interpretation and 005 boundary

rc0はSOLVER_ACCEPTED_NOT_TRANSACTION_PROOF。診断取得の成功とinstall transactionの証明を分ける。
004BはSIGNED_SOLVER_TRANSACTION_PROOF、canonical transaction/fingerprint、005 handoffを生成しない。
source構成でcandidateやrc/codeが変わっても、それだけで004の原因確定とはしない。
必要な安全診断が得られた後、別の固定transaction候補・別identity・別owner approvalを要する。
005の準備/launch/installは今回0。

## Offline evidence

testsはfake text/fake indices/no-exec/no-socket kernel guardのみ。
今回APT network/simulation/update/download/install、dpkg mutation、Docker、VOICEVOX、FFmpeg、MP4、
artifact/cache upload、user PC実行は0。synthesis/encode/publishingその他runtimeも0。
main/production/n8n/V1/existing YouTube Pipeline/PR15/PR16は変更しない。
