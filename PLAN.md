# Plan — Media Downloader (for Dad)

Status: **v0.6.1 (2026-09-09): unreadable browser cookies are skipped rather than sinking every download, with a notice.
v0.6.0 the same day: Safari-cookies hint, one language for dubs and subtitles, WAV/AIFF, Settings + Help
dialogs, default choices in Settings, open in the OS player, Library playlists (multi-select, add to playlist,
browse one, open its folder), compact icon rows.** v0.5.1 the same day slimmed the bundle (QuickJS-ng for Deno, no
ffprobe). Dad reported v0.4.1 "works" on Windows. Phase 5 to-do list
reviewed and reordered 2026-09-09 — small fixes first (Safari-cookies hint, one language setting, WAV/AIFF,
Settings modal, Help), then folder default, Library polish, playback, an app window.

## Goal

A double-click desktop app (Windows, Linux, macOS) where a non-technical user pastes one or many
YouTube / Vimeo / Bandcamp URLs (videos, playlists, albums), picks **Audio** or **Video** and a quality,
and gets correctly tagged files straight into a folder of their choice, with per-item progress.

Primary user: Adam's dad. Audio quality matters; often audio-only (MP3) is all that's wanted.

## Decisions (2026-09-06)

- **Runs on Dad's machine, not hosted.** YouTube bot-blocks datacenter IPs (GCP etc.); Adam has no always-on
  home device; a public site needs auth and attracts abuse; local means files land directly in his folders.
- **Three targets, one codebase, built by CI.** GitHub Actions matrix (`windows-latest`, `ubuntu-latest`,
  `macos-latest`) on a tag push → GitHub Release assets. Nothing cross-compiles Python bundles from a Mac
  (checked: Briefcase needs a Windows host for Windows; PyInstaller is host-only).
- **Packaging: PyInstaller `onedir`** (`onefile` trips Windows Defender). Windows: zip (+ Inno Setup installer
  later). Linux: AppImage **plus tar.gz fallback** (AppImage needs `libfuse2` on some distros). macOS: `.app`/`.dmg`.
  Unsigned for now → one-time "Run anyway" / right-click Open.
- **yt-dlp via the official executable** (subprocess, `-J` for info, `--progress-template` for JSON
  progress), **self-updated with `yt-dlp -U` on every launch** so YouTube churn never needs an app release.
  Bundled binaries: `yt-dlp`, static `ffmpeg`, and a JavaScript runtime for YouTube's challenges — `deno` until
  2026-09-09, now `qjs` (QuickJS-ng, 2 MB vs 93 MB; ~4 s slower per YouTube link). `ffprobe` dropped the same day
  (yt-dlp only requires it for things this app never does). See Phase 5 → "Slim the bundle".
  - **Use the *onedir* zip builds (`yt-dlp_macos.zip` etc.), never the single-file executable.** Measured
    2026-09-06 on the Intel Mac: single-file = ~23 s *per launch* (it unpacks ~100 MB every time and macOS
    security-scans the new files); onedir = 23 s once, then 0.7 s. `-U` works on the onedir variant.
  - The wrapper **never falls back to a `yt-dlp` on PATH** — Adam's Mac has a stale 2024 one in
    `/usr/local/bin` and it fails in confusing ways ("no such option: --js-runtimes").
  - With Deno on PATH, yt-dlp's default clients return the full format list (53 formats to 2160p);
    no `player_client` overrides needed.
  - **Bundling** (found 2026-09-06): PyInstaller rewrites every executable it collects, even from `datas` —
    it thinned the universal `yt-dlp_macos` to a 73 KB stub and re-signed deno/ffmpeg, and yt-dlp then died with
    "Could not load PyInstaller's embedded PKG archive". `bin/` is therefore copied into the finished bundle
    verbatim by `scripts/bundle_binaries.py`, never listed in the spec. Also: a frozen parent leaks `_PYI_*`
    env vars and `LD_LIBRARY_PATH` to children (scrubbed in `ytdlp.clean_frozen_env`), and frozen Python has
    no CA bundle (`certifi` for the release check).
  - **Windows Defender vs PyInstaller** (found by Adam on the v0.4.0 zip, 2026-09-06): Defender quarantined
    `MediaDownloader.exe` as a threat and "dismiss" did nothing — the classic unsigned-PyInstaller-bootloader
    false positive. Windows therefore ships **no custom exe**: python.org embeddable runtime (PSF-signed
    `pythonw.exe`) + pip-installed package + Inno Setup installer with a shortcut to `pythonw.exe -m app.launcher`.
  - **Audio** (checked 2026-09-06): `-x --audio-format best` keeps the native codec (`.opus` from YouTube, `.mp3`
    from Bandcamp); `--audio-format m4a` on YouTube's `140` stream is a copy (FixupM4a), no re-encode;
    `--embed-thumbnail` needs `--convert-thumbnails jpg` (YouTube serves webp); missing subtitles don't fail.
  - **Vimeo** (checked 2026-09-06): every yt-dlp client needs a login now — public videos included — so
    Vimeo support means browser cookies. Bandcamp and YouTube work anonymously.
  - **yt-dlp prints the `postprocess` progress template to stderr** (found 2026-09-09, 2026.08.19), the
    `download` one to stdout. The wrapper reads both, else "Converting audio" / "Adding cover art" never show.
  - **Processes run via plain `subprocess` in worker threads, not asyncio subprocesses.** On Windows,
    uvicorn `--reload` uses a SelectorEventLoop, which can't spawn processes (found on the Windows 11 box,
    2026-09-06). Threads work on every loop; progress callbacks are marshalled back onto the loop.
    Backend CI runs on Windows too, with a fake-yt-dlp test suite for the plumbing.
- **Python 3.13** (Adam: 3.13.5 at `/usr/local/bin/python3`). **Frontend:** Vite 7, React 19, TypeScript,
  Tailwind v4, TanStack Query, shadcn/ui.
- **Sites:** extractor allowlist — YouTube + `youtube:tab` (playlists), Vimeo, Bandcamp (+ album).
  Anything else is rejected with a plain message.
- **Repo (decided 2026-09-06):** one **public** repo, renamed `adam-tuoa/media_downloader`, releases attached
  to it. Rationale: yt-dlp front-ends are common and public; a public repo means Dad's download link and the
  in-app update check work without a GitHub login, and CI minutes are free. README carries a personal-use note.
- **`MODE=local|hosted` switch** kept in config so a hosted copy stays possible, but auth / Library /
  rate limiting are out of scope until someone wants them.
- **Trim/clip ranges:** later.

## Architecture

**Backend — Python 3.13 / FastAPI**
- `ytdlp.py` wrapper around the binary: probe (`-J`, `--flat-playlist` for lists), download (JSON progress lines,
  `--print after_move:filepath` for the final path), self-update.
- Job model in SQLite (app-data dir via `platformdirs`): `jobs` → `items`. Worker pool, default 2 concurrent.
- API: `POST /jobs`, `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `DELETE /jobs/{id}`,
  `GET/PUT /settings`, `POST /open-folder`, `POST /quit`, `POST /update-ytdlp`.
- Localhost guard: bind `127.0.0.1` on a free port; per-launch random token required in a header; `Origin` check.
  (Without this any website Dad visits could drive his downloader.)
- Serves the built UI from `backend/app/static/`.

**Frontend — Vite 7 / React 19 / TS / Tailwind v4**
- One screen: URL textarea → Audio|Video + quality → Start. Jobs board with per-item progress, errors, retry.
  Settings (output folder, concurrency). "Open folder", "Quit". Mobile-ish layout, big targets, plain words.

**Packaging — Phase 4**
- `scripts/fetch_binaries.py` downloads yt-dlp/ffmpeg/deno for the current platform into `backend/bin/`
  (gitignored) — used by dev and CI alike.
- PyInstaller spec → launcher starts server, opens browser. App-update banner from GitHub Releases API.

## Phases

Each phase leaves the app working. Tests + CI land in Phase 0 so later phases stay green.

### Phase 0 — Cleanup & toolchain
- [x] Delete dead code: `app.py`, `backend/app/routes/`, `backend/app/util/`, `frontend/src/Index.tsx`,
      `frontend/src/components/YouTubeDownLoader.tsx`
- [x] Rebuild `.venv` on Python 3.13.5; `backend/pyproject.toml` replaces `requirements.txt`; bump FastAPI/uvicorn/pydantic
- [x] `scripts/fetch_binaries.py` (yt-dlp, ffmpeg, deno) + `ytdlp.py` subprocess wrapper; drop the pinned yt-dlp library
- [x] Format listing done right: include video-only (DASH) streams, best-per-height, `filesize_approx` fallback,
      thumbnail/uploader/duration, audio formats in the same response
- [x] Download: `<id>+bestaudio/best` merge, path from yt-dlp output (not directory scanning), non-blocking
      (no sync yt-dlp inside `async def`), real error messages passed through to the UI
- [x] Fix the gremlins: audio preset key mismatch (`audio` vs `audio-only`), `selectedFormat` not reset on preset
      change, duplicated filter logic, `format_filesize` mutating its arg, `nocheckcertificate` removed
- [x] Frontend: Vite 7, React 19, Tailwind v4 (`@tailwindcss/vite`), deps actually declared in `package.json`,
      `VITE_API_URL`, show backend error detail
- [x] Tooling: ruff, pytest (fixtures = saved `yt-dlp -J` output), eslint + prettier, vitest; GitHub Actions CI (lint + test) — 25 pytest + 9 vitest tests
- [x] Docker: removed (Dockerfiles referenced files that no longer exist); hosted mode is Phase 5
- [x] README rewritten (Python 3.13, Deno, ffmpeg, how to run)

### Phase 1 — Job model
- [x] SQLite (stdlib `sqlite3` — an ORM wasn't worth freezing into the bundle) in app-data dir; `jobs` / `items` tables; survives restart
- [x] Worker pool: asyncio queue, N concurrent subprocesses, progress parsed into DB (throttled), cancel kills the whole process tree (ffmpeg included)
- [x] Jobs API (see Architecture) + settings API
- [x] Jobs board UI: progress bars, per-item status/errors, retry, clear finished; settings page
- [x] Output folder delivery via `.incomplete/<item>/` then a collision-safe move; filename template `%(title)s [%(id)s].%(ext)s`; "Open folder" / "Show file" (`open -R` / `explorer /select` / `xdg-open`)
- [x] Probe result reused for the download (`--load-info-json`) — one metadata extraction per item, not two

### Phase 2 — Batch & playlists
- [x] Multi-URL textarea; URL normalisation (`youtu.be`, `/shorts/`, `/live/`, strip `&t=`/`&list=` noise); dedupe
- [x] Playlist / album expansion (`--flat-playlist -J`), entry-selection UI, one item per entry
- [x] Extractor allowlist (YouTube, youtube:tab, Vimeo, Bandcamp, Bandcamp album) with clear rejection message
- [x] One bad URL never stops the batch; per-item retry
- [x] "Use cookies from <browser>" setting (`--cookies-from-browser`) — Vimeo currently requires login even
      for public videos; also unlocks private / members-only / age-checked YouTube
- [x] Per-stream progress labels ("Downloading video" / "Downloading audio") so a merge doesn't look like a restart
- [x] Friendly hints prepended to yt-dlp errors people can act on (cookies, private, unavailable)
- [x] `MD_ALLOW_ANY_SITE=1` escape hatch for Adam's own use

### Phase 3 — Audio & quality
- [x] Audio modes: **Original** (Opus → `.opus`, or `.m4a` when source is AAC), **M4A** (AAC), **MP3** 320/192/128
      — labelled plainly ("MP3 320: most compatible; can't be better than the original")
- [x] Tags + cover art: `--embed-metadata --embed-thumbnail --convert-thumbnails jpg`, `--parse-metadata` for artist/title
- [x] Video ladder 360p → 2160p (4K option in the UI): prefer h264+aac MP4 ≤ 1080p, vp9/av1 above; plain labels
- [x] Optional subtitles (`--write-subs --embed-subs`)
- [x] Any playlist/album → one folder per collection, `01 - ` numbering (`%(track,title)s`); `[id]` suffix dropped from filenames
- [x] Audio-language preference (Settings, default English) for YouTube's dubbed tracks — found by Adam: the
      highest-bitrate track on a multi-language video was Indonesian, so video downloads got the wrong language
- [x] Windows "Show file" fix: Explorer's `/select,` must be one quoted argument, else it opens Documents (found on the Win11 box)

### Phase 4 — Desktop app
- [x] Launcher: free port, per-launch token (HttpOnly SameSite=Strict cookie via `/launch`), open browser, single-instance check via `instance.json`, `POST /api/quit`; logs to `app.log`
- [x] `vite build` → `backend/app/static/`, served by FastAPI
- [x] PyInstaller spec (`onedir`, windowed), bundles `bin/` + `static/` — 330 MB, builds in ~70 s, verified end to end on the Mac
- [x] `yt-dlp -U` on launch (queue starts after it) + Settings → "Update now" + "engine isn't working" notice when yt-dlp fails
- [x] App-update check against GitHub Releases → banner with link
- [x] Release workflow (`release.yml`): tag `v*` or manual → Windows zip, Linux tar.gz (ubuntu-22.04), macOS zip
      (`macos-15-intel`); attaches to a GitHub Release with `packaging/RELEASE_NOTES.md`. AppImage deferred (FUSE support cost)
- [x] First-run notes in the release body and README
- [x] Smoke-tested the CI-built v0.4.1 builds: Windows installer on the PC (installed, opened, downloaded — no
      Defender/SmartScreen quarantine), macOS zip on the Mac after `xattr -cr` (Sequoia's Open Anyway didn't work)

### Phase 5 — Later

Done:
- [x] **Library (2026-09-09, v0.5.0):** a page listing everything ever downloaded, from `jobs.sqlite3`
  — title, thumbnail, site, format/quality, when, and whether the file is still where it was put (moved/deleted
  files shown as such, not hidden). Actions: open file / show in folder when present, **Download again** (re-queue
  the same URL with the same options — the whole point when a file has gone), remove from history. Search by title.
  Cheap because the data is all there already: `items.file_path` + `os.path.exists`, and jobs know their options.

To do, roughly in order of value for effort (list reviewed with Adam 2026-09-09):

**Small — an afternoon or less each**
- [x] **Safari cookies on macOS need Full Disk Access — done 2026-09-09.** Adam's Vimeo attempt with "Use cookies from: Safari"
      failed with `[Errno 1] Operation not permitted: ~/Library/Cookies/Cookies.binarycookies` — macOS privacy
      (TCC) blocking the app — and the hint wrongly said "set Use cookies from in Settings". Recognise that
      message and say so plainly: "macOS is blocking Safari's cookies. System Settings → Privacy & Security →
      Full Disk Access → add Media Downloader (or Terminal when running from source), then try again. Firefox
      and Chrome don't need this." Also in Help and the README.
- [x] **One language for dubbed audio and subtitles — done 2026-09-09.** Settings gets a single "Language" (used for YouTube's
      dubbed audio *and* subtitles); the form keeps only the subtitles checkbox, whose text reads "Include
      <Language> subtitles when the video has them" from that setting. "Original (as uploaded)" → subtitles in the video's own language (`info["language"]`, else
      English). `subtitle_args()` takes the language; the worker passes `settings.audio_language` (key can stay).
- [x] **WAV and AIFF audio — done 2026-09-09.** WAV is a plain `--audio-format wav`; AIFF isn't in `-x`'s list (checked on yt-dlp
      2026.08.19) but is in `--remux-video`/`--recode-video`, so `-f bestaudio --recode-video aiff`. Label
      honestly: uncompressed, for editing, ~10× the size, no better than the original. yt-dlp's thumbnail
      embedder refuses both containers, so `tag_args` skips `--embed-thumbnail` for them. Verified: WAV gets
      title/artist/date (INFO chunk), AIFF gets full ID3 tags including chapters (`Metadata:-write_id3v2 1`).
- [x] **Settings as a modal — done 2026-09-09** (an overlay with `role="dialog"`, not `<dialog>`: jsdom can't
      drive `showModal()`); the same `Modal` serves Help.
- [x] **Help button — done 2026-09-09** → in-app guide: pasting links, Audio vs Video, where files go, signing in (cookies, the
      macOS Full Disk Access step), updating the engine, when things go wrong. Mostly the README and
      release-notes text reworded for Dad.

- [ ] **Slim the bundle** (430 MB installed on macOS; downloads 139 MB Windows / 169 MB macOS / 235 MB Linux).
      Measured 2026-09-09 on the Mac: deno 93 MB, yt-dlp onedir 124 MB (its own Python 3.14 framework, universal2,
      plus curl_cffi/OpenSSL), ffmpeg 77 MB, ffprobe 77 MB, our Python + app ≈ 60 MB. Steps, cheapest first:
      1. [x] **Drop ffprobe (−77 MB) — done 2026-09-09.** yt-dlp only *requires* it for things we never do
         (concat, HLS fixup, embedding info-json, thumbnails in MKV — we always merge to MP4 — and the third-choice
         thumbnail method for m4a after mutagen); codec detection falls back to `ffmpeg -i`. The one reachable
         path (a last chapter with no end time → ffprobe for the duration) is closed by `ytdlp.complete_chapters`.
      2. [x] **QuickJS-ng instead of Deno (−91 MB) — done 2026-09-09.** `--no-js-runtimes --js-runtimes
         quickjs:<path>` (needs quickjs-ng ≥ 0.12; binaries 1–3 MB, the Linux one static). Measured on the Intel
         Mac: a YouTube probe takes 11.5 s vs 7.2 s with Deno, so ~4 s more per YouTube item (the download reuses
         the probe via `--load-info-json`, no second solve). Windows arm64 gets the x86_64 exe (no native build).
         **Verified on the Windows 11 PC 2026-09-09:** no Defender prompt for `qjs.exe`; YouTube video + MP3 and a
         Bandcamp album downloaded with cover art; the "Converting audio" stage now shows (the stderr fix).
      3. **yt-dlp as a library, not its own exe (≈ −105 MB on macOS, less on Windows).** Run `yt_dlp` inside our
         Python in a subprocess (the frozen app re-invokes itself with a flag); self-update by fetching the
         `yt-dlp` + `yt-dlp-ejs` wheels from PyPI into the app-data dir (a wheel is a zip; no pip needed) and
         putting that dir first on `sys.path`. Needs mutagen (+ pycryptodomex) in our bundle. Bonus: far fewer
         files for macOS to scan on first launch. Replaces the `-U` mechanism — medium.
      4. **A minimal ffmpeg (~10 MB instead of 77).** We only mux (mp4/mkv/webm), encode MP3 (lame), AAC and
         PCM, and convert thumbnails; a custom `--disable-everything` build per platform in CI is the most work
         of the lot. Middle options: BtbN's lgpl build (smaller, unmeasured) or imageio-ffmpeg's 25–31 MB
         static binaries (MP3 encoder presence unverified).
      5. Small stuff: `uvicorn` without `[standard]` (uvloop, watchfiles, websockets… ≈ 8 MB), `tar.xz` for
         the Linux download, PyInstaller excludes.
      After 1+2 (2026-09-09): `bin/` is 202 MB on macOS, was 371 — the app should land near 260 MB (release
      build not yet measured). Floors: 1–3 ≈ 155 MB; all five ≈ 80 MB. A 40 MB installer that fetches the tools on first
      run is also possible (the fetch script already exists) but cuts only the download, not disk.

- [x] **Default choices in Settings (Adam, 2026-09-09; done the same day):** what new downloads start with —
      Video or Audio, video quality, audio format — pre-selects the form. Stored as the UI's own choice keys
      (`default_kind`, `default_video`, `default_audio`), validated but not interpreted by the backend.

**Medium — a day or two each**
- [ ] **First-run setup instead of a silent default folder** (Adam, 2026-09-09: don't assume Music or any other
      folder). When no settings are stored yet, show a one-time setup: the download folder (pre-filled with
      `Downloads/Media Downloader`, with a note that Windows Storage Sense / macOS can auto-clean Downloads) and
      the language. Saving writes both, so later default changes never move anyone. No country setting: geo-blocks
      are by IP address, yt-dlp's country flag only fakes a header YouTube ignores, and dubbed audio and subtitles
      are keyed by language.
- [x] **Library polish — done 2026-09-09.** Compact rows (Adam's call, same day): icon-only buttons inline on the
      right with tooltips and accessible names (`lucide-react`; `IconButton`), the On disk / Missing pill small
      in the meta line; the selection toolbar keeps icon + word (`ActionButton`). Same on the board; checkbox multi-select with a toolbar (select all, "Remove selected", "Move to
      folder…", clear); the move dialog names a folder (existing groups offered as chips, blank = back to the main
      folder): files go under `<output>/<group>/` via `move_into` (never overwriting) and the items' `collection`
      becomes the group, so *Download again* lands there too. Missing files are skipped and named in the result.
      `POST /api/library/remove`, `POST /api/library/move`; `groups` in the library page.
      **Called "playlists" in the UI (Adam, 2026-09-09):** on disk they're folders, in the app they behave like
      playlists, and Dad thinks in YouTube playlists. Playlist chips across the top of the Library filter it
      (`?group=`, in playlist order), the playlist name in a row does the same, and "Open folder" beside the
      active chip reveals its folder (`/api/reveal` with `group`). "Add to playlist…" is the move.
- [x] **Open in the OS player — done 2026-09-09.** The thumbnail and the title of any finished download, on the
      board and in the Library, open the file with whatever the OS uses for it (`open` / `os.startfile` /
      `xdg-open`; `POST /api/items/{id}/open`, 404 when the file has gone). An in-app player (`GET /api/library/{id}/file`, Starlette 1.6
      `FileResponse` handles Range requests, behind `<video>`/`<audio>`) stays optional; note `.opus` and the
      vp9/av1 MP4s from 1440p/2160p may not play in Safari.
- [ ] **A window instead of a browser tab.** Cheapest: Chromium "app mode" — launch Edge (always present on
      Windows), Chrome or Chromium with `--app=<launch URL>` when one is installed, else the default browser as
      now. No tabs or address bar, own taskbar entry, zero new dependencies. Next step up: pywebview (native
      WKWebView / WebView2; Linux needs system webkit2gtk, so keep the browser fallback there). Tauri (listed
      before) would replace the launcher and packaging — not worth it. A window changes nothing about cookies:
      `--cookies-from-browser` reads the user's real browser. The real cookie fix, if Safari/Chrome keep biting,
      is an in-app "Sign in to Vimeo" webview that exports its cookies to a `cookies.txt` for yt-dlp — needs
      pywebview. **Clean shutdown (Adam, 2026-09-09):** Quit stays (it only shows in desktop mode — closing the
      tab leaves an invisible `pythonw.exe` behind). Add an *idle shutdown* with the window: the UI polls
      `/api/health` every minute, so when no page has checked in for ~2 minutes and nothing is downloading, the
      server exits by itself. Works for a tab, app mode (no close event) and pywebview alike; never kills a batch.

**Unchanged from before**
- Linux AppImage (needs libfuse2 on the user's machine; tar.gz ships first)
- App icon (.icns / .ico) and a signed macOS build (Developer ID, US$99/yr) if the right-click-Open dance bothers anyone
- Trim/clip ranges (`--download-sections`)
- `MODE=hosted`: auth, Library + retention, rate limits, Docker with ffmpeg + deno
- Pre-probe preview in the form ("Check link" from Phase 0) if Dad wants to confirm before queueing
- `watch?v=X&list=Y` links: offer "just this video / the whole playlist" instead of always taking the video
- Channel links (`/@name`): accept as a capped playlist
- **Facebook / Instagram** (Adam asked 2026-09-09). yt-dlp has both extractors. Facebook: public videos and reels
  mostly work anonymously (`facebook.com/watch`, `/reel/`, `/videos/`, `fb.watch` short links); private or group
  videos need cookies. Instagram: nearly everything needs a signed-in browser's cookies, the extractor breaks often,
  and automated access can get the account temporarily flagged — set expectations before adding it. The work
  itself is small: allowlist entries + link normalisation + tests. Try a real link first with `MD_ALLOW_ANY_SITE=1`.
- "Batch finished" desktop notification

## Open questions — resolved "keep it flexible" (2026-09-06)
- **Linux:** distro unknown → ship both AppImage and tar.gz; x64 assumed.
- **Audio player:** unknown → offer Original / M4A / MP3; **default MP3 320** (plays everywhere), labelled honestly.
- **Windows v1:** plain zip with `.exe`; Inno Setup installer only if the zip proves awkward for Dad.
- **Test machines:** Adam's Mac (**Intel**, macOS Sequoia 15.7.9) and a Windows 11 box. macOS build must be
  x86_64 (Intel CI runner); add arm64 later if anyone needs it.

## Risks
- **First launch after install or a yt-dlp update takes ~20-30 s on macOS only** (Gatekeeper scanning the new
  binaries; Windows 11 measured as "not long", 2026-09-06). The macOS build should show a "first-time setup"
  message rather than look hung; Windows/Linux need nothing.
- **YouTube churn** — mitigated by yt-dlp self-update + a bundled JS runtime (QuickJS-ng); still expect occasional breakage. Clear in-app error + update button.
- **Unsigned binaries** — one-time OS warnings; document. Apple signing (US$99/yr) optional later.
- **AV false positives** on `yt-dlp.exe` / PyInstaller output on Windows — `onedir` reduces; document.
- **Local API exposure** — token + Origin guard from day one of Phase 4.

## Windows 11 dry run (2026-09-06) — passed
Python 3.14 + Node LTS (winget) on Adam's Windows 11 box: `fetch_binaries.py` fetched the win64 yt-dlp/deno/ffmpeg
builds without incident, `yt-dlp.exe`'s first launch was quick, no SmartScreen/Defender prompts (script-downloaded
files carry no mark-of-the-web), probes and downloads work with and without `--reload` after the threaded-subprocess
fix. The only prompt seen was UAC for the Node installer.

## Environment notes (Adam's Mac, 2026-09-06)
- Intel Mac, macOS Sequoia 15.7.9. Python 3.13.5 at `/usr/local/bin/python3` (3.12.11 also present). Existing `.venv` is pyenv 3.9.1 → delete and rebuild.
- Node 24.14 / npm 11.9 via nvm. ffmpeg 6.0 at `/usr/local/bin/ffmpeg`. Deno not installed (`brew install deno`, or via `fetch_binaries.py`).
- `frontend/node_modules` exists but `package.json` doesn't declare tailwind/postcss/lucide — fixed in Phase 0.
- Verified 2026-09-06: pinned yt-dlp 2023.10 / 2024.10 fail on every video; latest works, `android_vr` client gave 33 formats to 2160p without Deno.
