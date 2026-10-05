# 004D fixed config-field diagnostic — offline preparation

Identity `manual-fixture-runtime-preflight-20261005-004d`; no marker during
preparation. A separately approved preparation parent and one marker-only Added
commit are the only future launch authorization. Read-only contents/actions,
exact marker push path, exact repository/event/readiness branch, attempt 1,
complete marker/history guard and output approval gates remain required.
004C is permanently consumed at aca72b4ef40d644c180cf1f0885096903f5f3793; run
37263821548 is retained and never retried. 001/002/004/004B remain consumed.
003 blocked/unconsumed and actual render unconsumed. No 005 workflow or installer.

## Audit and frozen evidence

004C's apt-get/cache/config were version2.8.3 and rc0; apt-config dump rc0 was
followed by RUNTIME_APT_CONFIG_FAILED in verification/parser. Lists/index/policy/
simulation were not reached. No dump was retained, so the failing key is unknown.
The old verify_config rejects every repeated key, including anonymous list entries.
Official APT syntax supports tree/list nodes, so this is a demonstrated parser
compatibility defect, not proof of the actual run's cause. Empty scope nodes and
unknown valid defaults can also occur. Old code/evidence remain intact.

## Fixed-key authority and supplementary safety inspection

22 scalar fields are checked individually using `/usr/bin/apt-config shell
PLM_VALUE FIXED_KEY`, once each, in plan/code allowlist order. Output is parsed as
one inert assignment, never evaluated. It is compared in memory against expected
private paths / exact fixed values. Only field ID and matched flag are published.
A missing scalar, duplicate assignment, malformed output or rc failure stops.
Empty required values must appear explicitly as an empty assignment; absence
fails closed. Shell quoting variants beyond the deliberately narrow supported
single-quote grammar also fail closed. Runtime formatting compatibility has NOT
been proven by synthetic tests and remains a separate future-run check.

APT::Architectures uses a separate list parser. A single bounded apt-config dump
is supplementary ONLY for list, hook, RootDir and binary-specific override safety;
it is not the source of scalar field values. Flattened tree empty parent nodes and
repeated anonymous :: entries are supported; duplicate amd64 entries do not become
scalar duplicate errors. Architecture values must remain amd64 only. Unknown
valid defaults and their anonymous lists are ignored and never copied as evidence.
Malformed output, nonempty dpkg/APT hooks, host RootDir/source overrides or required
scalar duplicates stop. Raw dump/value/paths and unknown key names are never emitted.

All required fields: status/lists; source list/parts; config main/parts;
preferences/parts; trusted keyring/parts; cache/pkgcache/srcpkgcache; dpkg;
Architecture/Architectures; recommends/suggests; Download/Simulate; retries;
insecure repositories/unauthenticated. dpkg=/bin/false and isolated RUNNER_TEMP
sources/config/status/lists/cache are retained, no host config writes.

Public reasons: FIELD_MISSING, FIELD_VALUE_MISMATCH, SCALAR_DUPLICATE,
LIST_FORMAT_UNSUPPORTED, FORBIDDEN_HOOK_PRESENT, HOST_SOURCE_LEAK,
MALFORMED_CONFIG_OUTPUT, QUERY_FAILED. All use RUNTIME_APT_CONFIG_FAILED plus the
allowlisted field ID/reason. Fixed field start records are flushed before queries,
and completed matches are retained if a later field fails. No observed values.

## Gated continuation and bounds

Only after all scalar and supplementary config checks PASS may the future run
continue status verification, signed private lists, APT policy and bounded resolver
diagnostics from004C. No package/root version changes. Ten distinct singleton
requests and one combined request maximum, once each, no retry. No transaction
proof/fingerprint or install authorization is claimed by this diagnostic.
Private status read occurs for config construction before verification; its
initial read label is not evidence that snapshot verification passed.

This preparation executes only guarded fake tests/offline CI. APT runtime/network,
simulation, package download/install/change, dpkg mutation, Docker, VOICEVOX,
FFmpeg/media, artifact/cache upload, D1/Worker/AI/YouTube/SNS and user PC are zero.

Official interface references (not evidence of actual runner output):
- https://manpages.ubuntu.com/manpages/noble/man8/apt-config.8.html — shell key queries
- https://manpages.ubuntu.com/manpages/noble/man5/apt.conf.5.html — tree/list syntax
