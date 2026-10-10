# Architecture Decision Records

An ADR records one project decision: the context, the choice, the alternatives rejected, and the evidence. Every project decision has exactly one ADR in this directory, written from [template.md](template.md).

## Status values

| Status | Meaning |
|---|---|
| Proposed | The decision has a planned answer that a named gate (a measurement or test) will confirm or change. The Gate section states the test and its pass condition. |
| Accepted | The decision is in force. A partly amended ADR keeps it, with a pointer: `Accepted; <part> amended by ADR-XXXX`. |
| Superseded by ADR-XXXX | A later ADR replaced this decision. |
| Deprecated | The decision no longer applies and nothing replaced it. |

## Rules

- An Accepted ADR is never rewritten. A changed decision gets a new ADR that supersedes the old one; only the old ADR's status line changes.
- File names are `NNNN-kebab-title.md`, numbered in order of creation.
- A new decision or a changed decision gets its ADR in the same change that implements it.

## Index

| Number | Title | Status | Module | Note |
|---|---|---|---|---|
| [0001](0001-bge-m3.md) | Embedding model BAAI/bge-m3 with 30-second windows | Accepted | M5 | |
| [0002](0002-ollama-call-contract.md) | Ollama call contract (qwen3.5:latest) | Accepted | M0 | |
| [0003](0003-record-architecture-decisions.md) | Record architecture decisions | Accepted | M0b | |
| [0004](0004-configuration-system.md) | Configuration system | Accepted | M0b | |
| [0005](0005-development-restart-and-build-order.md) | Development restart and walking-skeleton build order | Accepted | Project | |
| [0006](0006-scope-asr-baseline-visual-optional.md) | Scope: ASR pipeline is Baseline, visual pipeline is Optional | Accepted | Project | |
| [0007](0007-visual-track-effort-allocation.md) | Visual track effort allocation | Proposed | V1-V3 | |
| [0008](0008-feature-tiers-and-numbering.md) | Feature tiers and numbering | Accepted | Project | |
| [0009](0009-runtime-platform-and-file-layout.md) | Runtime platform and file layout | Accepted | M0 | |
| [0010](0010-ollama-hosting-and-networking.md) | Ollama hosting and networking | Accepted | M0 | |
| [0011](0011-gpu-discipline-one-model-in-vram.md) | GPU discipline: one model in VRAM at a time | Accepted | Project | |
| [0012](0012-llm-selection-and-vram-headroom.md) | LLM selection and VRAM headroom | Proposed | M7 / M11 | |
| [0013](0013-asr-engine-faster-whisper.md) | ASR engine: faster-whisper | Accepted | M4 | |
| [0014](0014-asr-checkpoint-and-language-setting.md) | ASR checkpoint and language setting | Superseded by ADR-0039 | M4 | Superseded by ADR-0039 |
| [0015](0015-query-time-embedding-on-cpu.md) | Query-time embedding on CPU | Proposed | M5 | |
| [0016](0016-dense-sparse-retrieval-rrf.md) | Dense + sparse retrieval with Reciprocal Rank Fusion | Proposed | M5 / M9 | |
| [0017](0017-window-edges-and-overlap.md) | Window edges and overlap | Proposed | M5 | |
| [0018](0018-hybrid-retrieval-architecture.md) | Hybrid retrieval architecture | Accepted | Project | |
| [0019](0019-concept-canonicalisation-across-scripts.md) | Concept canonicalisation across scripts | Proposed | M8 | |
| [0020](0020-importance-and-recap-flags-on-extraction-pass.md) | Importance and recap flags ride on the extraction pass | Accepted | M7 | |
| [0021](0021-deferred-infrastructure.md) | Deferred infrastructure | Accepted | Project | |
| [0022](0022-job-queue-sqlite-single-gpu-worker.md) | Job queue: SQLite + single GPU worker | Superseded by ADR-0033 | M1 | |
| [0023](0023-workspace-caching-and-session-rule.md) | Workspace caching and session rule | Superseded by ADR-0034 | M1 | |
| [0024](0024-link-ingestion-download-and-play-locally.md) | Link ingestion: download and play locally | Accepted | M3 | |
| [0025](0025-media-normalisation-and-workspace-layout.md) | Media normalisation and workspace layout | Superseded by ADR-0034 | M2 / M3 | |
| [0026](0026-player-integration-point-seekto.md) | Player integration point: seekTo(seconds) | Accepted | M3 / M6 | |
| [0027](0027-api-server-and-ui-stack.md) | API server and UI stack | Accepted | M3 / M6 | |
| [0028](0028-code-organisation-backend-src-vs-tools.md) | Code organisation: backend/src vs tools/ | Accepted | Project | |
| [0029](0029-textbook-for-book-grounded-features.md) | Textbook for book-grounded features | Accepted | M0b | |
| [0030](0030-book-page-numbering-index-and-label.md) | Book page numbering: index and printed label | Proposed | M10 | |
| [0031](0031-visual-ocr-engine-and-isolation.md) | Visual OCR engine and isolation | Proposed | V1-V3 | |
| [0032](0032-repository-visibility-and-content-policy.md) | Repository visibility and content policy | Accepted | Project | |
| [0033](0033-job-queue-worker-and-resume-model.md) | Job queue, worker and resume model | Accepted | M1 | Supersedes ADR-0022 |
| [0034](0034-workspace-identity-chained-stage-keys-and-privacy-rule.md) | Workspace identity, chained stage keys and privacy rule | Accepted | M1 | Supersedes ADR-0023 |
| [0035](0035-link-ingestion-on-the-runner.md) | Link ingestion on the runner: chain root, provisional workspace, rebind | Accepted | M1 | Amends ADR-0034 (first-stage upstream key, `gdrive` source kind) |
| [0036](0036-local-file-ingestion-and-shared-media-normalisation-policy.md) | Local-file ingestion and shared media normalisation policy | Accepted | M2 | Amends ADR-0035 (`normalise` is shared; uploaded originals are deleted, link originals are kept) |
| [0037](0037-http-upload-transport.md) | HTTP upload transport: raw streamed body, one upload at a time, no CORS | Accepted | M2 | |
| [0038](0038-no-empty-edits-in-video-mp4.md) | video.mp4 must not rely on an empty edit to stay in sync | Accepted | M2 | Amends ADR-0036 (late audio or video is re-encoded; new post-verify rule) |
| [0039](0039-asr-checkpoint-and-language-setting-decision.md) | ASR checkpoint and language setting: large-v3 with `language="ur"` | Accepted | M4 | Supersedes ADR-0014; language setting amended by ADR-0040 |
| [0040](0040-lecture-language-selection-and-whisper-language-mapping.md) | Lecture language selection and Whisper language mapping | Proposed | M4 | Amends ADR-0039 (language: per-lecture choice; Hindi -> `ur` is the only tested entry) |
| [0041](0041-system-output-language-is-english.md) | System output language is English | Proposed | Project | |
| [0042](0042-asr-stage-design.md) | ASR stage design | Proposed | M4 | |
