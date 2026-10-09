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
# Flash at 5.0 s and beep at 5.0 s on the container clock; the audio stream starts 1.5 s late (the MP4 edit-list case).
ff -f lavfi -i "color=c=black:s=640x360:r=25:d=15,drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(t,5.0,5.2)'" \
   -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$out/_flash.mp4"
ff -f lavfi -i "aevalsrc=exprs='if(between(t\,3.5\,3.7)\,0.5*sin(2*PI*1000*t)\,0)':s=48000:d=15" -c:a aac "$out/_beep.m4a"
ff -i "$out/_flash.mp4" -itsoffset 1.5 -i "$out/_beep.m4a" -map 0:v -map 1:a -c copy "$out/flash_beep_delayed_audio.mp4"
rm -f "$out/_flash.mp4" "$out/_beep.m4a"
head -c 3221225472 /dev/zero > "$out/dummy_3GB.mp4"
ls -la "$out"
