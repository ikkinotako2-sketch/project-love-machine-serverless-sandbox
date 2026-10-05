# 004F resolver-debug boundary preparation

Identity `manual-fixture-runtime-preflight-20261005-004f` is unconsumed. No marker is created by this preparation. 004E and its run 37285242354 remain permanently consumed; no retry/rerun/resume. 003 remains blocked/unconsumed. Actual render remains unconsumed. No 005 workflow or installer is prepared.

004E evidence is frozen in `runtime-preflight-v4e-frozen-evidence.json`: scalar 22/22, all supplementary scopes, status, nine private lists and all ten exact root policies passed. ffmpeg singleton reached solver entry with rc100; only the debug parser failed; remaining simulations were zero. This evidence does not establish the underlying dependency conflict. Configuration, root package versions, official sources and signed root package evidence are unchanged.

## Source audit and compatibility limits

The legacy `apt_startup_v4c.parse_debug()` accepts entry/end, a minimal Broken relationship, Investigating, Considering and fixed dependency errors. Every other nonempty line stops. It omits source-defined selection/rejection messages and PrettyDep's version/state annotation of the target. Its historical code and tests remain intact; only the new candidate uses `apt_resolver_debug_v4f`.

Read-only inspection of Ubuntu Noble APT 2.8.3 at source commit `c9fece91ff1cf0ac4e0d272978d3bd8669161989` supplies the output templates in `apt-pkg/algorithms.cc` and the PrettyPkg/PrettyDep formatting in `apt-pkg/prettyprinters.cc`. `debian/changelog` identifies 2.8.3. Their immutable retrieval hashes match the initially inspected Noble-updates source. URLs and raw-file SHA256 values are recorded in `apt-resolver-v4f-source-evidence.json`. This is an implementation-derived subset, **not an official stable or exhaustive APT debug grammar**. Source investigation was read-only; source files are neither fetched by the runtime candidate nor required by offline CI.

The 27 fixtures in `apt-resolver-v4f-source-fixtures.json` instantiate source output templates with fake trusted packages. They are not an actual APT execution recording. They include selection/rejection, reinstatement, signed Broken relationship annotations, ResolveByKeep messages and the benign Show Scores header. ShowScores is not enabled by this candidate; recognition of its exact header does not permit arbitrary score lines.

## Boundary

Classification precedes strict family parsing. Public families: RESOLVER_START, RESOLVER_END, INVESTIGATING, CONSIDERING, BROKEN_DEPENDENCY, PACKAGE_SELECTION, PACKAGE_REJECTION, DEPENDENCY_SUMMARY, USER_FACING_DEPENDENCY_ERROR, BENIGN_DIAGNOSTIC and UNSUPPORTED_RELEVANT_SYNTAX.

Only exact, source-confirmed benign syntax may be accepted without dependency evidence. Unknown benign-looking text is unknown relevance and stops; there is no unconditional ignore. Unknown decision syntax, unknown package, unverified/malformed version, unsupported architecture/state syntax, or relationship not present in signed Depends/Pre-Depends/Conflicts/Breaks stops with RUNTIME_APT_RESOLVER_DIAGNOSTIC_FAILED. Unversioned relationships and signed alternative members are supported, but alternative membership is not a provider selection or solver proof. Observed installed versions are checked against private status. Candidate fields come from verified index/private status context. Required versions are authorized by the signed relationship, even when no downloadable package has that constraint boundary version.

Each unsupported report contains only fixed syntax_family, relevance, known_package_tokens_count and fixed_reason. Recognized reports contain only trusted package/dependency/version/relation fields and fixed family/reason. Raw line/stdout/stderr/exception text is never published or retained. Stderr is bounded to 64 KiB in memory; line length 2,048; evidence 500 rows and conflicts 100. Overflow stops safely. No claim that all APT 2.8.3 families will parse successfully; an unsupported family remains a diagnostic stop, without consuming another simulation.

## Future separately approved launch

Exact readiness-branch marker-only push, repository/event/branch job condition, read-only contents/actions permissions, single-parent approved preparation and complete marker-history guard remain the sole authorization route. No marker means no runtime. All previous safety flags remain true. 004E is rejected as consumed by both primary launch guards.

The existing config/index/policy stages remain before resolver entry. First simulation is ffmpeg only. Only safe parsing of that result permits the other nine distinct singleton inputs and then the combined root10. Maximum 11 distinct inputs, each once; no retry/fallback/debug second launch. rc100 safely parsed is diagnostic evidence, not resolver success or an install authorization. On unsupported syntax, last safe solver entry/count and fingerprint survive; remaining inputs do not execute.

Package binary download/install/remove/upgrade/downgrade, dpkg mutation, Docker, VOICEVOX, FFmpeg runtime, media, artifacts/cache, external publishing and user PC execution remain zero. `transaction_proof=false` and `install_authorized=false` on success and failure. Main/production/n8n/existing YouTube Pipeline are untouched.
