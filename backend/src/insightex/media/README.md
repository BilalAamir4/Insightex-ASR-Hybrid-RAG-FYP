# insightex.media

**Purpose:** Media handling (audio extraction, video serving).

**Model used:** none (FFmpeg, CPU only: no -hwaccel, no NVENC)

**Feature numbers:** not assigned

**Status:** `ffmpeg.py`: ffprobe inspection, remux-vs-transcode decision, libx264 transcode (crf 23, preset
medium, <=1080p, CFR, yuv420p) with `-progress` parsing, 16 kHz mono WAV extraction, JPEG thumbnails.
Video serving not yet.
