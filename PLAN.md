# Plan — Media Downloader (for Dad)

Status: Phase 1 complete 2026-09-06. **Next: Phase 2.**

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
  Bundled binaries: `yt-dlp`, static `ffmpeg`, `deno` (yt-dlp's recommended JS runtime for YouTube challenges).
  - **Use the *onedir* zip builds (`yt-dlp_macos.zip` etc.), never the single-file executable.** Measured
    2026-09-06 on the Intel Mac: single-file = ~23 s *per launch* (it unpacks ~100 MB every time and macOS
    security-scans the new files); onedir = 23 s once, then 0.7 s. `-U` works on the onedir variant.
  - The wrapper **never falls back to a `yt-dlp` on PATH** — Adam's Mac has a stale 2024 one in
    `/usr/local/bin` and it fails in confusing ways ("no such option: --js-runtimes").
  - With Deno on PATH, yt-dlp's default clients return the full format list (53 formats to 2160p);
    no `player_client` overrides needed.
  - **Processes run via plain `subprocess` in worker threads, not asyncio subprocesses.** On Windows,
    uvicorn `--reload` uses a SelectorEventLoop, which can't spawn processes (found on the Windows 11 box,
    2026-09-06). Threads work on every loop; progress callbacks are marshalled back onto the loop.
    Backend CI runs on Windows too, with a fake-yt-dlp test suite for the plumbing.
- **Python 3.13** (Adam: 3.13.5 at `/usr/local/bin/python3`). **Frontend:** Vite 7, React 19, TypeScript,
  Tailwind v4, TanStack Query, shadcn/ui.
- **Sites:** extractor allowlist — YouTube + `youtube:tab` (playlists), Vimeo, Bandcamp (+ album).
  Anything else is rejected with a plain message.
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
- [ ] Multi-URL textarea; URL normalisation (`youtu.be`, `/shorts/`, `/live/`, strip `&t=`/`&list=` noise); dedupe
- [ ] Playlist / album expansion (`--flat-playlist -J`), entry-selection UI, one item per entry
- [ ] Extractor allowlist (YouTube, youtube:tab, Vimeo, Bandcamp, Bandcamp album) with clear rejection message
- [ ] One bad URL never stops the batch; per-item retry

### Phase 3 — Audio & quality
- [ ] Audio modes: **Original** (Opus → `.opus`, or `.m4a` when source is AAC), **M4A** (AAC), **MP3** 320/192/128
      — labelled plainly ("MP3 320: most compatible; can't be better than the original")
- [ ] Tags + cover art: `--embed-metadata --embed-thumbnail --convert-thumbnails jpg`, `--parse-metadata` for artist/title
- [ ] Video ladder 360p → 2160p: prefer h264+aac MP4 ≤ 1080p, vp9/av1 above; plain labels
- [ ] Optional subtitles (`--write-subs --embed-subs`)
- [ ] Bandcamp album → one folder per album, track numbers in filenames

### Phase 4 — Desktop app
- [ ] Launcher: free port, per-launch token, open browser, single-instance check, `POST /quit`
- [ ] `vite build` → `backend/app/static/`, served by FastAPI
- [ ] PyInstaller spec (`onedir`), bundles `bin/` + `static/`
- [ ] `yt-dlp -U` on launch (background, with timeout) + "Update yt-dlp" button + honest error when YouTube breaks
- [ ] App-update check against GitHub Releases → banner with link
- [ ] Release workflow: matrix build on tag → `win-x64.zip`, `linux-x64.AppImage` + `.tar.gz`, `mac-x64.dmg`
      (Intel macOS runner — Adam's Mac is Intel)
- [ ] First-run notes (SmartScreen / `chmod +x` / `libfuse2`); smoke-test on clean Windows + Linux VMs

### Phase 5 — Later
- Trim/clip ranges (`--download-sections`)
- `MODE=hosted`: auth, Library + retention, rate limits, Docker with ffmpeg + deno
- Native window + signed auto-updater via Tauri
- Pre-probe preview in the form ("Check link" from Phase 0) if Dad wants to confirm before queueing
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
- **YouTube churn** — mitigated by yt-dlp self-update + Deno; still expect occasional breakage. Clear in-app error + update button.
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
