# One-shot executor / cloud runtime preflight offline preparation

Status: **BLOCKED_ONE_SHOT_EXECUTOR**. Offline state machine and a separate
cloud runtime preflight candidate are implemented. Neither workflow is enabled.
No live renderer adapter is present. Existing 1,572 PASS receipt is preserved,
not rerun, overwritten or relabelled. New CI validates new code plus regressions.

## Fixed boundaries

- Baseline sandbox head: `aa3f224319f7686842ac7b681ed16c24cf27f958`.
- Baseline CI: `37201445190`, 625 Python + 947 Node = 1,572 PASS, 0 FAIL.
- Branch: `plm-offline-readiness-v1-20261002` only; production/main/n8n/V1/
  existing YouTube pipeline/PR15/PR16 untouched.
- Render identity: `manual-fixture-render-20261004-001`.
- Fixture: `manual-japanese-script-fixture-v1`, existing canonical bytes unchanged.
- Production renderer: `25f24bc4e6a20164c5549f746fc0eefcedf5d178`; existing raw
  source pins are checked by the new offline executor. Source snapshot remains
  an offline oracle, NOT an executable fork or runtime source of truth.
- Runtime candidate: `voicevox/voicevox_engine@sha256:ab700b3768d0a2e9230d53e054b321f60409fda34fe794a333ae7202ab1c87f4`.
- Official tag `cpu-amd64-ubuntu24.04-0.25.2`, linux/amd64; index digest
  `sha256:ece7d29fb87c754f795c044e13436d2181fccf8d50560bd45160c705b4f7e8d9`
  is NOT the execution manifest. ARM64 is never accepted.
- Expected `/version`: `0.25.2`; `/speakers`: exactly one style ID 1, name
  `ずんだもん`, style `あまあま`. Build ENGINE 0.25.2 specifies VVM 0.16.4.
- User Windows/Chromebook/WSL/Docker Desktop/local Docker/Python/FFmpeg/
  VOICEVOX/server/always-on PC are forbidden execution platforms. Scratch is
  the Codex cloud authoring environment, not a user PC. Future runtime must be
  standard GitHub-hosted `ubuntu-24.04` X64; PC power-off has no effect.

## Owner billing evidence

`owner-billing-evidence-20261004.json` records the user's screenshot
transcription as OWNER evidence, NOT connector telemetry or a new screenshot
inspection. Oct 1–4 billed amount $0; current-month metered usage exists;
displayed payment region has no saved method and billing fields are unfilled;
owner will not add a card. Actions, Packages, Codespaces, Git LFS, All AI Credit
SKUs are budget $0 / Stop usage Yes. No billing API mutation exists in candidates.

This is a fail-closed no-paid-upgrade boundary under GitHub's documented budget
enforcement, not a proof of reserved/free remaining storage capacity. The three
allowed artifact files total <=12 MiB, retention 1 day, upload <=1. Quota,
billable storage requirement, upload failure or unknown means STOP, no retry,
budget/card changes, extra artifact/cache, or retention extension. Safe summary
must say result persistence failed, not render success. No actual upload adapter
is wired in the candidate. Actual future upload action must explicitly disable
internal automatic retries as well as workflow retries or remain BLOCKED.

## History one-shot candidate and its permanent-ledger limitation

The identity is hard-coded; no workflow input permits identity substitution.
`run_attempt==1`, additionally `run_number==1`, a fixed concurrency group and
`cancel-in-progress:false` are required. Read-only workflow runs API pages use
NO branch/status/event/head filters. All pages are read with stable total_count,
duplicate/missing-current/binding/changed-history validation and a 20-page bound.
Any other run of the workflow consumes the identity regardless of conclusion:
cancelled, failed setup, success, timeout, skipped, unknown all reject. No API
retry or side-effect retry occurs. A second run_number is rejected even when a
previous record is missing. Original workflow ID and approved code SHA must be
bound before a future metadata preflight can run.

**GitHub run records have a delete API.** The published run_number contract is
scoped to a particular workflow; it does not prove permanent identity evidence
survives workflow deletion/recreation or administrative history changes. Neither
concurrency nor a current-run-only response proves an undeletable lifetime ledger.
Thus `permanent_ledger_proven=false`, and `live_render_gate()` unconditionally
STOPs with `BLOCKED_PERMANENT_CONSUMPTION_HISTORY_MUTABLE`. Changing policy flags
does not unlock it. No D1, user-PC ledger or repository mutation during runtime
has been substituted. The offline history candidate is useful, but is not a
PASS on the user's strict permanent-consumption requirement.

The offline executor counts an attempt BEFORE invoking its in-memory effect.
The same object cannot resume even after setup/encode/upload failure. The receipt
explicitly says OFFLINE_SIMULATION_PASS_NOT_LIVE_READY and actual_operations=0.
Fake effects only return in-memory observations; they never create media or run
production Python. Unknown exception bodies are not retained.

## Fixed future render sequence (offline oracle only)

1. GitHub Actions run record created (identity consumed in the proposed history scope).
2. run_attempt=1 and run_number=1 check.
3. Fixed workflow/identity complete prior-run history check.
4. Consumed/binding decision; permanent-consumption gate must also be resolved.
5. Fixture SHA checks: script `9077ccd4b61ff3bcdadcccaaea90219377acfd4abf19ebd414af36f7eb7c0b8b`,
   normalized `dbcc62dfe12ef550bb37987839c6cd3e30743ca9bc307d6f8131d42e7e0f555e`,
   payload `2b92b1b2266da9be38e0cebdd061add724734049f08afc0bbffbe06b7aa53c40`.
6. Production exact commit checkout (never mutable main or sandbox renderer fork).
7. Renderer raw hashes.
8. Exact VOICEVOX AMD64 manifest/platform evidence.
9. Cloud runtime binaries/version/filter/encoder/font and codec dependency lock.
10. Container start once.
11. `/version` GET once.
12. `/speakers` GET once.
13. Exact style ID 1 / ずんだもん / あまあま match.
14. Synthesis <=1.
15. FFmpeg encode <=1.
16. Quality Gate (read-only decoding/probes are not extra encodes).
17. Exact artifact inventory and <=12 MiB cap.
18. Upload <=1; internal retries must be disabled in a future uploader.
19. Safe receipt/summary; no narration, provider bodies, tokens, or raw speaker body.

Any mismatch, exception, timeout or unknown stops before the next effect. A failed
artifact upload is NOT success. Automatic retry/rerun/resend/fallback=0. No real
render dispatch or approval is requested by this preparation.

## Separate cloud metadata preflight candidate

Identity: `manual-fixture-runtime-preflight-20261004-001`; never consumes the
render identity. Both YAML workflows have job `if:false`, allow=false,
execution_approved=false. Preflight JSON also has hard_disabled=true. Both
policy and environment must be separately approved; original registered workflow
ID and approved head are owner-reviewed repository variables, currently unset.
The preflight and render histories are distinct.

The preflight checks complete history before setup, then checks again before
runtime effects. It requires GitHub-hosted/Linux/X64/Ubuntu24.04. Candidate Python
3.12.15 distribution exists for Linux24.04 x64. No apt install occurs: exact
FFmpeg `7:6.1.1-3ubuntu5`, ffprobe 6.1.1, Noto CJK `1:20230817+repack1-3`,
required filters/encoders and selected Noto Sans CJK JP font must already be
available; absence or drift STOPs without switching to apt latest. It records
libav, libx264 and libass package versions; external codec dependency pinning
remains necessary before real render, and the receipt does NOT claim it is locked.
Docker version/availability is checked only on the GitHub-hosted runner.

After official registry revalidation, one docker pull command and one container
start are candidates, with no restart policy. A fixed 15-second startup window
precedes exactly one GET /version, then one GET /speakers. These are the ONLY
allowed loopback URLs. No POST, audio_query, synthesis, initialize/warmup call,
generation, FFmpeg encode, MP4, artifact upload, YouTube/SNS is present. Cleanup
is one docker rm command even if start outcome is unknown; cleanup failure is
STOP, not a retry. Docker's own layer-transfer behavior is not asserted to be
one physical network request; workflow/application automatic retries remain 0.

**Dispatch registration blocker:** the new preflight file is absent from sandbox
default branch `main` (read-only 404 checked during preparation). GitHub requires
workflow_dispatch files on the default branch. Main is prohibited from changing,
so this candidate cannot be advertised as dispatch-ready. No existing workflow
was repurposed to bypass this restriction. Registration requires separate scope
resolution; no runtime approval is requested while this is unresolved.

## Quality Gate (unchanged)

MP4 exists; size strictly >10,000; video AND audio streams; 1080x1920; exact
30fps; duration 0.5–180.5 inclusive; captions.ass exists with Dialogue:; maximum
decoded frame YAVG >=25; mean volume >=-38 dB. Production's >=10,000 condition
remains untouched; the oracle adds the one-shot strict >10,000 gate. No threshold
changes after execution. No OCR or actual rendered-video PASS is claimed.

## Validation and evidence

New tests run under the existing native no-exec/no-socket guard and use only
fake adapters/text fixtures. All previous files/tests/receipts/workflows are
unchanged. A new offline CI run is permitted for the new code; existing run
37201445190 is not rerun. CI is NOT runtime preflight. Final remote head must be
read back for both disabled workflows; exact counts are recorded in a new receipt.

Official sources:

- https://docs.github.com/en/rest/actions/workflow-runs#delete-a-workflow-run
- https://docs.github.com/en/actions/reference/workflows-and-actions/variables
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/billing/concepts/budgets-and-alerts
- https://hub.docker.com/v2/repositories/voicevox/voicevox_engine/tags/cpu-amd64-ubuntu24.04-0.25.2
- https://github.com/VOICEVOX/voicevox_engine/blob/0.25.2/.github/workflows/build-engine.yml
- https://github.com/VOICEVOX/voicevox_vvm/blob/0.16.4/README.md
- https://github.com/actions/python-versions/releases/tag/3.12.15-36805895057
- https://packages.ubuntu.com/noble/amd64/ffmpeg/download
- https://packages.ubuntu.com/noble/all/fonts-noto-cjk/download

Actual runtime preflight dispatch, Docker pull/start, VOICEVOX requests, synthesis,
FFmpeg encode, MP4, artifact upload, D1 remote, Worker, AI inference, YouTube,
SNS, user PC execution: all 0. Billing settings/card changes: 0.
