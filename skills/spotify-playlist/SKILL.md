---
name: spotify-playlist
description: Mirror a Spotify playlist (or the newest N Liked Songs, the "top" list) to local MP3s with the spotifyDL pipeline - Exportify CSV in, official-version download, duration audit, vibe or mood folders, push to the phone. Use for "download my Spotify playlist", "grab my top songs", "refresh the karaoke folder", "put my playlist on my phone".
---

# /spotify-playlist

Runs `D:/repo/_Misc/Music/spotifyDL` end to end. Detail and flags: `D:/repo/_Misc/Music/spotifyDL/README.md:1` (the canonical how-to; this skill is the run order and the owner's conventions, not a copy). Single URLs go to `/grab-media` instead.

## Facts (do not re-derive)

- No Spotify API: the Web API 403s unless the app owner has Premium, so metadata comes from an Exportify CSV and `spotify_playlists.py` stays blocked.
- Toolchain: `python` 3.12, `yt_dlp` and `mutagen` modules, ffmpeg at `~/.spotdl/ffmpeg.exe` (no ffprobe; durations come from mutagen). Missing ffmpeg: `python -m spotdl --download-ffmpeg`.
- "Top N" playlist = the **N newest Liked Songs**: the first N rows of the Liked Songs export (Exportify lists newest `Added At` first). Verified on the 2026-08 top-50 run and the 2026-11 top-200 run.
- Seasonal name (spotifyDL `docs/DECISIONS.md` SDL-1, SDL-5): `Top 200 <Season> <yy>`, used for both the local folder and the Spotify playlist. Winter = Nov-Jan, Spring = Feb-Apr, Summer = May-Jul, Fall = Aug-Oct; the year is the year the season starts.
- Run folder: one dated folder per run under the repo, e.g. `260902/`, holding the CSVs, `downloads/<Playlist>/`, `download.log` and `repair.log`. CSVs and MP3s are gitignored (the CSV holds the Spotify user ID).

## Steps

1. **Export (owner signs in, Claude in Chrome clicks).** The owner signs in at https://exportify.net (the Spotify access grant is theirs); then click Export on the playlist row and wait for the button to return from "Exporting". The CSV lands in the connected browser's download folder, which may not be `~/Downloads` (this machine's Brave uses `D:/Downloads`, and repeat exports get a ` (1)` suffix), so check its timestamp before using it. Copy it into a new run folder `<repo>/<yymmdd>/`. For the top list, slice the Liked export: `python -c "import csv,sys; n=int(sys.argv[3]); r=list(csv.reader(open(sys.argv[1],encoding='utf-8-sig'))); csv.writer(open(sys.argv[2],'w',newline='',encoding='utf-8')).writerows(r[:n+1])" "<liked.csv>" "<run>/<Name>.csv" 200` (n + 1 keeps the header).
2. **Prove on one track.** Slice a 1-row CSV the same way (`r[:2]`), run `download.py` on it into a scratch folder, and check the MP3 plays and has the YouTube URL in its ID3 comment. A failure here means fix the method, not run the batch.
3. **Download, in the background** (the 2026-08 run did 4 playlists, about 170 tracks, in 12 minutes): `python download.py --csv "<run>/<Name>.csv" --output "<run>/downloads/<Name>"`, one playlist after another, appending to `<run>/download.log`. Re-running skips files already on disk and retries failures.
4. **Audit.** `python audit.py --csv "<run>/<Name>.csv" --downloads "<run>/downloads/<Name>"`; if anything is flagged, rerun with `--fix` (replaces only when a closer official version exists, via temp-then-swap) and log to `<run>/repair.log`.
5. **Sort, by playlist kind.**
   - Curated playlists (Karaoke, Chills): stay flat. Never genre-classify them.
   - Dumping-ground playlists (Liked, the top list): `python classify.py --csv ... --downloads ... --reclassify --min-songs 8` (owner's minimum is **8**; the script default of 5 is wrong for this owner). Smaller buckets fold into the catch-all.
   - Karaoke moods: `python classify.py --mood --downloads "<run>/downloads/Karaoke"` (buckets from `karaoke_moods.json`, keyed by track URI). Preview any classify with `--dry-run` first.
   - New folder names follow `Personal Name (theme / genre)` and must not appear in the `used` list of `playlist_names.json`; add each new name to `used`.
6. **Album tags (optional):** `python tag_albums.py --downloads "<run>/downloads/<Name>"` so Samsung Music's Albums view groups by folder.
7. **Push to the phone:** phone unlocked, USB in File Transfer (MTP) mode, then `python push_to_phone.py --source "<run>/downloads" --only <Name>`. It needs Portage's WPD engine (`PORTAGE_DIR`, default `D:/repo/Data/portage`, with its venv). Without the phone, stop here and say the push is pending.
8. **File the seasonal playlist on Spotify (top list only).** In Claude in Chrome on Liked Songs: click a blank part of row 1, scroll to row N, shift-click a blank part of it, right-click, then Add to playlist > `Seasons` > New playlist. Avoid the album column (it navigates) and "Remove from your Liked Songs" (next to Add to playlist). Screenshot before each menu click, because a window resize closes the menu. The playlist starts named after its first song and public: open it, use Name and details to set the seasonal name, and confirm its song count is N.

## Pass/fail check (report this)

- Per playlist: MP3 count under `downloads/<Name>` equals the CSV's data rows, or the shortfall is listed by track.
- Audit report shows no flagged tracks, or each flag was kept on purpose (the Spotify cut has no YouTube match).
- After classify, no MP3 is left at the top of a classified playlist folder and no folder holds fewer than 8 songs except the catch-all.
- Push: the script's uploaded-file count, or "pending: phone not connected".
- Spotify: the seasonal playlist is inside `Seasons`, carries the seasonal name, and shows N songs.
