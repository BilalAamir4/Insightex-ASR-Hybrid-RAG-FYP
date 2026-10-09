#!/bin/bash
# Build the small files that BROWSER_CHECKLIST.md asks for, in a folder a Windows browser can open.
#   bash tools/m2_verify/make_browser_fixtures.sh [/mnt/e/FYP/m2_fixtures]
# Nothing is committed; the folder is yours to delete afterwards. The 3 GB dummy is for the cancel and
# close-tab steps (a real lecture uploads in under a second on this machine); the server rejects it as not a video.
set -euo pipefail
out="${1:-/mnt/e/FYP/m2_fixtures}"
mkdir -p "$out"
ff() { ffmpeg -hide_banner -loglevel error -nostdin -y "$@"; }
V=(-f lavfi -i "testsrc2=size=640x360:rate=25:duration=20")
A=(-f lavfi -i "sine=frequency=440:sample_rate=44100:duration=20")
X=(-c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac)
ff "${A[@]}" -c:a aac "$out/audio_only.m4a"
ff "${V[@]}" -f lavfi -i "sine=frequency=440:sample_rate=44100:duration=20,volume=0.0003" "${X[@]}" -shortest "$out/near_silent.mp4"
# Five flash/beep files. In each, a white flash (5.0-5.2 s) and a 1 kHz beep (5.0-5.2 s) coincide on the container
# clock, so a correct player shows them simultaneous. They differ in how the file stores the timeline:
FLASH="color=c=black:s=640x360:r=25:d=15,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,5.0,5.2)'"
FLASH_EARLY="color=c=black:s=640x360:r=25:d=15,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,3.48,3.68)'"
beep() { echo "aevalsrc=exprs='if(between(t\,$1\,$2)\,0.5*sin(2*PI*1000*t)\,0)':s=48000:d=15"; }
X264=(-c:v libx264 -preset ultrafast -pix_fmt yuv420p)
# 1. control: no offsets anywhere.
ff -f lavfi -i "$FLASH" "${X264[@]}" "$out/_v.mp4"
ff -f lavfi -i "$(beep 5.0 5.2)" -c:a aac "$out/_a.m4a"
ff -i "$out/_v.mp4" -i "$out/_a.m4a" -map 0:v -map 1:a -c copy "$out/control.mp4"
# 2. delayed_audio: the audio stream starts 1.5 s late (its beep is at 3.5 s in its own timeline).
ff -f lavfi -i "$(beep 3.5 3.7)" -c:a aac "$out/_a2.m4a"
ff -i "$out/_v.mp4" -itsoffset 1.5 -i "$out/_a2.m4a" -map 0:v -map 1:a -c copy "$out/delayed_audio.mp4"
# 3. delayed_video: the video stream starts 1.52 s late (its flash is at 3.48 s in its own timeline).
ff -f lavfi -i "$FLASH_EARLY" "${X264[@]}" "$out/_v2.mp4"
ff -itsoffset 1.52 -i "$out/_v2.mp4" -i "$out/_a.m4a" -map 0:v -map 1:a -c copy "$out/delayed_video.mp4"
# 4. transcode_bframes: HEVC + Opus, so it goes through the libx264 path (which uses B-frames).
ff -f lavfi -i "$FLASH" -c:v libx265 -preset ultrafast -x265-params log-level=error "$out/_v3.mkv"
ff -f lavfi -i "$(beep 5.0 5.2)" -c:a libopus "$out/_a3.opus"
ff -i "$out/_v3.mkv" -i "$out/_a3.opus" -map 0:v -map 1:a -c copy "$out/transcode_bframes.mkv"
# 5. copied_bframes: H.264 (default libx264 B-frames) + AAC in MP4. Eligible for copy, but the engine must transcode it.
ff -f lavfi -i "$FLASH" -f lavfi -i "$(beep 5.0 5.2)" -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac \
   -movflags +faststart -shortest "$out/copied_bframes.mp4"
rm -f "$out"/_v*.mp4 "$out"/_v3.mkv "$out"/_a*.m4a "$out"/_a3.opus
head -c 3221225472 /dev/zero > "$out/dummy_3GB.mp4"
ls -la "$out"
