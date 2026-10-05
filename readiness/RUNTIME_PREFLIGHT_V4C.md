# 004C APT startup/config diagnostic: offline preparation

Identity: `manual-fixture-runtime-preflight-20261005-004c`. No marker is created
in this preparation. Runtime needs a separately approved parent and a single
marker-only Added commit; complete marker/history guard, attempt 1, exact
repository/event/branch and output-only approval gates apply. Workflow permissions
are contents/read and actions/read. 004 and 004B remain permanently consumed,
with runs 37216447727 and 37260939639 retained; no retry/resume/rerun. 003 remains
blocked/unconsumed. Actual render stays independently unconsumed. No 005 code.

## Fixed stages and stop codes

| Stage | Code |
|---|---|
| apt_binary | RUNTIME_APT_BINARY_FAILED |
| apt_config | RUNTIME_APT_CONFIG_FAILED |
| status_snapshot | RUNTIME_APT_STATUS_FAILED |
| lists_layout | RUNTIME_APT_LISTS_LAYOUT_FAILED |
| index_visibility | RUNTIME_APT_INDEX_VISIBILITY_FAILED |
| root_policy | RUNTIME_APT_ROOT_POLICY_FAILED |
| resolver_start | RUNTIME_APT_RESOLVER_START_FAILED |
| resolver_debug | RUNTIME_APT_RESOLVER_DIAGNOSTIC_FAILED |

Fixed stage labels are flushed before each command and written to job summary.
Exceptions are converted to fixed codes, never copied as free text. Reports keep
only validated safe values and completed-stage evidence. Command output is bounded
in memory (stdout 2MB/stderr 64KiB, 120s) and never saved or printed verbatim.

## Future diagnostic scope

The GitHub-hosted ubuntu-24.04 / Python 3.12.15 candidate checks three absolute
APT binaries and their parsed versions, then verifies apt-config dump against
private status/lists/sources/cache, amd64, recommends/download false, retries zero,
and dpkg `/bin/false`. Host sources/config fragments/hooks cannot be used.
The private status must equal the host inventory byte-for-byte and by SHA256.
The initial read is recorded as status_snapshot before private config creation;
its verification follows apt_config. No system source/status is written.

Only Ubuntu archive signed Noble release/updates/security metadata is retrieved.
Existing root10 release versions, filenames and hashes stay unchanged. The release
cohort and keyring are pinned; updates/security cohorts are validated by signature,
manifest hash and index hash and their exact observed hashes reported. Nine private
list files (three InRelease and six uncompressed Packages) are verified. Each root
has exactly one apt-cache policy query before simulation: expected version must
have signed Ubuntu backing and be visible to APT itself. Python-only availability
is insufficient. Candidate must match the verified default policy, even if newer
than the requested root: no candidate is automatically adopted.

At most 10 distinct exact-version singleton simulations, then one distinct
10-root simulation. Each first and only attempt includes official
`Debug::pkgProblemResolver=true`; no second debug run and no retry. Unsupported
trace grammar, invisible index, missing entry marker or any stage failure stops
before remaining attempts. Debug parses only known package names, metadata-backed
constraints, installed/candidate versions and fixed conflict types. Trace text
and annotations are not evidence copied into reports. The grammar intentionally
fails closed; it does not guarantee every APT trace will be supported.

All commands use `--simulate --no-download --no-install-recommends`; there is no
binary download/install adapter. dpkg `/bin/false` is preserved: this diagnostic
may expose an APT startup/capability interaction rather than solve it. No root
cause is asserted in advance. rc=0 or parsed trace is diagnostic evidence only,
never SIGNED_SOLVER_TRANSACTION_PROOF or install authorization. A complete
canonical transaction/fingerprint is required before any separately approved005
preparation; this candidate does not create either.

## Frozen 004B evidence

All four cases rc100; root10 exact availability true; root candidate differences0.
Coverage: release 578; release+updates 1157; release+security 946; all three1162.
These observations alone prove neither dependency conflict nor config failure.
The structured frozen evidence is hashed by the new plan.

## Verification and boundary

Offline fake tests cover missing binaries/config leakage/status/hash mismatch,
private Packages present but APT invisible, candidate mismatch, solver not entered,
known/unknown debug grammar, secret-like output non-disclosure, marker independence
and consumed identities. No APT or metadata retrieval is executed in preparation.
No package/dpkg mutation, Docker, VOICEVOX, FFmpeg, media, artifact/cache upload,
D1/Worker/AI/YouTube/SNS, paid runner or user PC operation is permitted.

Official interface references: Ubuntu Noble manuals for apt-config(8), apt-cache(8)
and apt.conf(5), including Debug::pkgProblemResolver. These document the inspection
interfaces, not the failed run's root cause.
