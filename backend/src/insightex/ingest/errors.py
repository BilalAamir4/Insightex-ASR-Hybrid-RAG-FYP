"""The single ingestion error type: a machine-readable code plus a message fit for a student or teacher."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    UNSUPPORTED_URL = "UNSUPPORTED_URL"
    PLAYLIST_NOT_SUPPORTED = "PLAYLIST_NOT_SUPPORTED"
    LIVE_NOT_SUPPORTED = "LIVE_NOT_SUPPORTED"
    PRIVATE_OR_LOGIN_REQUIRED = "PRIVATE_OR_LOGIN_REQUIRED"
    AGE_RESTRICTED = "AGE_RESTRICTED"
    GEO_BLOCKED = "GEO_BLOCKED"
    DRIVE_NOT_SHARED = "DRIVE_NOT_SHARED"
    DRIVE_QUOTA_EXCEEDED = "DRIVE_QUOTA_EXCEEDED"
    TOO_LONG = "TOO_LONG"
    TOO_LARGE = "TOO_LARGE"
    NOT_A_VIDEO = "NOT_A_VIDEO"
    NO_AUDIO_STREAM = "NO_AUDIO_STREAM"
    BLOCKED_ADDRESS = "BLOCKED_ADDRESS"
    RIGHTS_NOT_CONFIRMED = "RIGHTS_NOT_CONFIRMED"
    NETWORK_ERROR = "NETWORK_ERROR"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    TRANSCODE_FAILED = "TRANSCODE_FAILED"
    # Added by M2 (ADR-0036). The shared normalise engine raises these for links and files alike.
    NO_VIDEO_STREAM = "NO_VIDEO_STREAM"
    EMPTY_FILE = "EMPTY_FILE"
    INSUFFICIENT_DISK = "INSUFFICIENT_DISK"
    UNSUPPORTED_CODEC = "UNSUPPORTED_CODEC"
    DURATION_UNKNOWN = "DURATION_UNKNOWN"
    TOO_SHORT = "TOO_SHORT"
    TRUNCATED = "TRUNCATED"
    SYNC_CHECK_FAILED = "SYNC_CHECK_FAILED"
    # Reserved for the HTTP upload (M2 session 2); nothing raises these yet.
    LENGTH_REQUIRED = "LENGTH_REQUIRED"
    UPLOAD_BUSY = "UPLOAD_BUSY"
    UPLOAD_INTERRUPTED = "UPLOAD_INTERRUPTED"


DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNSUPPORTED_URL: (
        "This link isn't supported. Paste a YouTube video link, a Google Drive file link, "
        "or a direct link to a video file."
    ),
    ErrorCode.PLAYLIST_NOT_SUPPORTED: (
        "Playlists aren't supported. Open the single video you want and paste its link."
    ),
    ErrorCode.LIVE_NOT_SUPPORTED: (
        "Live or upcoming streams can't be added. Try again once the recording has been published."
    ),
    ErrorCode.PRIVATE_OR_LOGIN_REQUIRED: (
        "This video is private or needs a sign-in. Only publicly viewable videos can be added."
    ),
    ErrorCode.AGE_RESTRICTED: "This video is age-restricted and can't be added.",
    ErrorCode.GEO_BLOCKED: "This video isn't available in our region, so it can't be added.",
    ErrorCode.DRIVE_NOT_SHARED: (
        "This Google Drive file isn't shared publicly. Set sharing to "
        "\"Anyone with the link\" and try again."
    ),
    ErrorCode.DRIVE_QUOTA_EXCEEDED: (
        "Google Drive has temporarily limited downloads of this file because it was downloaded "
        "too many times. Try again later, or upload the file directly."
    ),
    ErrorCode.TOO_LONG: "This video is too long.",
    ErrorCode.TOO_LARGE: "This video file is too large.",
    ErrorCode.NOT_A_VIDEO: "This doesn't look like a video file we can read.",
    ErrorCode.NO_AUDIO_STREAM: "This video has no audio track, so it can't be transcribed.",
    ErrorCode.BLOCKED_ADDRESS: "This link points to a private or local network address and can't be used.",
    ErrorCode.RIGHTS_NOT_CONFIRMED: (
        "Please confirm you have the right to use this video before adding it."
    ),
    ErrorCode.NETWORK_ERROR: "We couldn't reach the video's server. Check the link and try again.",
    ErrorCode.DOWNLOAD_FAILED: "The video couldn't be downloaded. Please try again later.",
    ErrorCode.TRANSCODE_FAILED: "The video file couldn't be processed. It may be damaged.",
    ErrorCode.NO_VIDEO_STREAM: "This file has no video track. Only video files can be added.",
    ErrorCode.EMPTY_FILE: "This file is empty.",
    ErrorCode.INSUFFICIENT_DISK: "There isn't enough free disk space to process this video.",
    ErrorCode.UNSUPPORTED_CODEC: "This video uses a format we can't read.",
    ErrorCode.DURATION_UNKNOWN: "We couldn't tell how long this video is, so it can't be added.",
    ErrorCode.TOO_SHORT: "This video is too short to add.",
    ErrorCode.TRUNCATED: "This video looks cut off or damaged: the processed copy is much shorter than the original.",
    ErrorCode.SYNC_CHECK_FAILED: "We couldn't line up the sound with the picture in this video, so it can't be added.",
    ErrorCode.LENGTH_REQUIRED: "The upload didn't say how large the file is.",
    ErrorCode.UPLOAD_BUSY: "Another upload is already in progress. Try again when it has finished.",
    ErrorCode.UPLOAD_INTERRUPTED: "The upload was interrupted. Please try again.",
}


class IngestError(Exception):
    """code: one of ErrorCode. message: shown to users. The underlying error is logged, not shown."""

    def __init__(self, code: ErrorCode | str, message: str | None = None) -> None:
        self.code = ErrorCode(code)
        self.message = message or DEFAULT_MESSAGES[self.code]
        super().__init__(f"{self.code}: {self.message}")

    def to_dict(self) -> dict[str, str]:
        return {"code": str(self.code), "message": self.message}


class IngestRejected(IngestError):
    """The media itself is unusable ("your file is unusable"), as opposed to an internal error ("we broke").

    `message` is user-facing and fixed per code; `details` (for example the tail of ffmpeg's stderr)
    goes to the job's stage error and the worker log, never to the user.
    """

    def __init__(self, code: ErrorCode | str, message: str | None = None, details: str = "") -> None:
        super().__init__(code, message)
        self.details = details
