# ADR-0024: Link ingestion: download and play locally

Status: Accepted
Date decided: 2026-10-06
Date recorded: 2026-10-08
Module: M3

## Context

Decided and verified 2026-10-06. A new requirement: ingest a lecture from a link, not only from an upload.

## Decision

One path for every source: fully download, then play locally. There is no embedded YouTube player and no audio-only path.

- Sources: YouTube (including the `/live/` URL shape), public Google Drive, direct URLs.
- yt-dlp handles YouTube and Drive (gdown removed). Deno in the venv is yt-dlp's JavaScript runtime.
- Limits: 3 hours (`ingest.url.max_duration_s: 10800`) and 4 GB (`ingest.url.max_download_bytes: 4294967296`).
- Rights confirmation is required before download.

## Alternatives considered

- Embedded YouTube player: rejected; one local path serves all sources.
- Audio-only path: rejected.
- gdown for Drive: removed in favour of yt-dlp.

## Consequences

Known gaps, none handled yet:
- Storage cleanup and quota are not designed.
- The yt-dlp Drive fallback is untested.
- The SSRF guard has a DNS-rebinding gap.
- HEVC decode is tested only on synthetic input.
- The demo-venue network is untested for YouTube downloads.

## Evidence

`.claude/rules/ingest.md`; `config/default.yaml` (`ingest.url`); `backend/src/insightex/ingest/`; `docs/BUILD_ORDER.md` (M3 done 6 Oct 2026).

## Gate / revisit when

Revisit when any known gap above is closed or a source type is added.
