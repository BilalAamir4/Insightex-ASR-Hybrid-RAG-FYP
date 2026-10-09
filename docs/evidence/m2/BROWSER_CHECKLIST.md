# M2 browser checklist (run by hand)

Run in a Windows browser against the WSL server. Nothing here has been run by the assistant: every **Result** is blank until you fill it in.

## Set up

1. In WSL, start the server and worker: `bash ~/insightex/scripts/dev_run.sh`
2. Open `http://127.0.0.1:8000/`. If the library already holds the Day 4 lecture, delete it first (steps 1 and 5 need it absent).
3. Make the extra files (writes to `E:\FYP\m2_fixtures`, about 3 GB; delete the folder afterwards):
   `bash ~/insightex/tools/m2_verify/make_browser_fixtures.sh`
4. Day 4: `E:\FYP\data\day04_batch_vs_online\raw\lecture_test.mp4` (688 s, SHA-256 `de27cb67...`).

Write down the browser and version: ____________________

| # | Step | Expected | Result (pass/fail, notes) |
|---|---|---|---|
| 1 | Under "Upload a file", click the drop zone (or press Enter on it), pick the Day 4 file from `E:\`. Tick the rights box. Click Upload. | File name and size shown. Upload button stays disabled until the box is ticked. After the upload the job view appears (Receive file, Convert video and audio) and ends at "Ready". Lecture is in the library. | |
| 2 | Delete that lecture, then drag `lecture_test.mp4` from Explorer onto the drop zone. Tick the box, upload. | Same outcome as step 1. The zone highlights while you drag over it. | |
| 3 | Upload `dummy_3GB.mp4` (tick the box) and watch the bar. | The bar moves; text shows percent, MB sent of total, and MB/s. | |
| 4 | Upload `dummy_3GB.mp4` again, click **Cancel upload** at about 30%. Then in WSL run `ls ~/insightex-data/staging`. Then upload `near_silent.mp4`. | Message "Upload cancelled." Staging folder is empty within a few seconds. The new upload works (no "another upload in progress"). | |
| 5 | Upload the Day 4 file again (after step 1/2 left it in the library). | Page opens the lecture with the note "This lecture is already in your library." No new job in `insightex jobs list`. | |
| 6 | Upload `audio_only.m4a`. | Job fails with a clear message ("This file has no picture, only sound. Upload a video file."). No lecture is added. | |
| 7 | Choose any file but leave the rights box unticked. Try to press Upload; try Enter/Space on the button. | Upload button is disabled and nothing is sent. Ticking the box enables it; unticking disables it again. | |
| 8 | Open the Day 4 lecture. Press play, then in the browser console run `insightex.seekTo(300)`. | Playback jumps to 5:00 (player shows 5:00). What the speaker says at 5:00 matches the transcript at 300 s: ____________ | |
| 9 | Start uploading `dummy_3GB.mp4`, then close the tab (or press F5) while the bar is moving. | The browser shows its "Leave site?" warning. Choosing Stay keeps the upload going. When no upload is running, closing gives no warning. | |
| 10 | Upload `near_silent.mp4`, open it in the player. | A yellow notice under the title: "The audio is very quiet, so the transcript may be poor." | |
| 11 | Upload `flash_beep_delayed_audio.mp4`, open it, scrub to 0:04.5 and play. This covers the MP4 edit-list case, which ffmpeg-based measurement cannot. | The white flash (at 5.0 s) and the beep (at 5.0 s) look and sound simultaneous. Note any lag you notice: ____________ | |

## After

- Delete the lectures you added (Delete button in the library) and `E:\FYP\m2_fixtures`.
- If any step fails, note the browser console output and `~/insightex-data/logs/worker.log`.
