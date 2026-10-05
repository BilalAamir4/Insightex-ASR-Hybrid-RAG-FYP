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
    ErrorCode.NOT_A_VIDEO: "This link doesn't point to a playable video.",
    ErrorCode.NO_AUDIO_STREAM: "This video has no audio track, so it can't be transcribed.",
    ErrorCode.BLOCKED_ADDRESS: "This link points to a private or local network address and can't be used.",
    ErrorCode.RIGHTS_NOT_CONFIRMED: (
        "Please confirm you have the right to use this video before adding it."
    ),
    ErrorCode.NETWORK_ERROR: "We couldn't reach the video's server. Check the link and try again.",
    ErrorCode.DOWNLOAD_FAILED: "The video couldn't be downloaded. Please try again later.",
    ErrorCode.TRANSCODE_FAILED: "The video file couldn't be processed. It may be damaged.",
}


class IngestError(Exception):
    """code: one of ErrorCode. message: shown to users. The underlying error is logged, not shown."""

    def __init__(self, code: ErrorCode | str, message: str | None = None) -> None:
        self.code = ErrorCode(code)
        self.message = message or DEFAULT_MESSAGES[self.code]
        super().__init__(f"{self.code}: {self.message}")

    def to_dict(self) -> dict[str, str]:
        return {"code": str(self.code), "message": self.message}
