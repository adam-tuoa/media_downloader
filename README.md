# Media Downloader

A small, friendly desktop downloader for YouTube, Vimeo and Bandcamp, built on
[yt-dlp](https://github.com/yt-dlp/yt-dlp). Paste links — videos, playlists, albums — pick
**Video** at a quality or **Audio** in the format you like, and the files land in a folder with
cover art and tags. See [PLAN.md](PLAN.md) for the decisions and what's done.

This is for personal use. Please respect the terms of the sites you download from and the
rights of the people who made the videos and music.

**Status:** v0.6.0 — a desktop app for Windows, macOS and Linux. Paste links (videos,
playlists, albums), pick the entries you want, choose Video (quality, optional subtitles in your
language) or Audio (MP3 / M4A / best original / WAV / AIFF), watch per-item progress; files land in
a folder of your choice with cover art and tags, albums and playlists in their own numbered folders.
A **Library** keeps the record of everything downloaded — with *Download again* for files that have
since moved. Settings (folder, language, what new downloads start with, browser cookies) and a
short in-app Help open as dialogs. Sites: YouTube, Vimeo, Bandcamp.

## Install (the desktop app)

Grab the file for your computer from the
[downloads page](https://github.com/adam-tuoa/media_downloader/releases/latest) — a Windows
installer, a macOS zip or a Linux tar.gz — and follow the three-line instructions there. The app opens in
your browser; **Quit** stops it. It updates its downloader engine (yt-dlp) on every launch and
tells you when a new app version exists. Windows shows SmartScreen's "Run anyway" once; on macOS
(not notarized) run `xattr -cr "Media Downloader.app"` once before the first launch — Sequoia's
"Open Anyway" route proved unreliable.

Developer notes on how that build is made are under [Packaging](#packaging).

## Stack

- **Backend:** Python 3.13, FastAPI, driving the official `yt-dlp` executable (not the library —
  the executable self-updates, which matters because YouTube changes constantly)
- **Frontend:** React 19, TypeScript, Vite, Tailwind v4, TanStack Query
- **Bundled tools:** `yt-dlp`, `ffmpeg`, `qjs` (QuickJS-ng — yt-dlp needs a JavaScript runtime to
  solve YouTube's challenges; its default Deno is 93 MB, QuickJS is 2 MB and about four seconds slower
  per YouTube link) — downloaded into `backend/bin/` by a script, never committed

## Setup

Requirements: Python 3.13, Node 24 (or 22+), git. No system ffmpeg needed — it's fetched.

```bash
# 1. Python environment
python3.13 -m venv .venv
.venv/bin/pip install -e "backend[dev]"

# 2. Helper binaries (~200 MB, once). The first yt-dlp launch is slow on macOS while the OS
#    scans the new files — the script does that launch for you, so expect ~30 s here.
.venv/bin/python scripts/fetch_binaries.py

# 3. Frontend
cd frontend && npm install
```

### Windows (PowerShell)

```powershell
# Tools - skip any you already have; close and reopen the terminal after installing.
winget install Git.Git
winget install OpenJS.NodeJS.LTS
py --list                      # needs 3.13 or newer listed

git clone https://github.com/adam-tuoa/media_downloader.git
cd media_downloader
py -3 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -e "backend[dev]"
.venv\Scripts\python scripts\fetch_binaries.py     # ~200 MB download; Defender may pause on yt-dlp.exe once
cd frontend; npm install; cd ..
```

Calling `.venv\Scripts\...` directly avoids activating the venv (and PowerShell's execution-policy prompt).

## Run (development)

Two terminals:

```bash
# backend on :8000
cd backend && ../.venv/bin/uvicorn app.main:app --reload      # Windows: cd backend; ..\.venv\Scripts\uvicorn app.main:app --reload

# frontend on :5173 (proxies /api to the backend)
cd frontend && npm run dev
```

Open <http://localhost:5173>.

To try the packaged layout instead — FastAPI serving the built UI from one port — run
`npm run build` (outputs to `backend/app/static/`) and open <http://localhost:8000>.

## Checks

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .   # python lint/format
(cd backend && ../.venv/bin/pytest)                          # python tests (no network needed)
(cd frontend && npm run lint && npm run typecheck && npm test && npm run build)
```

CI runs the same on every push (`.github/workflows/ci.yml`).

## How it works

Pasted lines are first normalised and checked (`POST /api/links`): `youtu.be/x`, `/shorts/x`
and `watch?v=x&list=…` all become the same video; playlist and album links are listed with
`yt-dlp --flat-playlist` so the user can tick the entries they want; anything that isn't YouTube,
Vimeo or Bandcamp is refused with a plain message (and yt-dlp itself is run with
`--use-extractors` so it can never fall back to its generic extractor). Only then does
submitting create a **job** with one **item** per link. A worker inside the API process
takes queued items (two at a time by default), probes each with yt-dlp, downloads it into
`<output folder>/.incomplete/<item id>/`, and moves the finished file into the output folder
(never overwriting — a duplicate gets ` (1)` appended). Progress goes into a SQLite database that
the UI polls once a second while anything is active. Interrupted items are re-queued on restart.

| What | Where |
|---|---|
| Jobs database | macOS `~/Library/Application Support/MediaDownloader/`, Windows `%LOCALAPPDATA%\MediaDownloader\`, Linux `~/.local/share/MediaDownloader/` — override with `MD_DATA_DIR` |
| Downloads (default) | `<your Downloads folder>/Media Downloader/` — change it in Settings |

## Library

The *Library* view lists every finished download from the jobs database, newest first, with
search and whether each file is still where the app put it. *Download again* re-queues the same
link with the options it was downloaded with — useful once a file has been moved or deleted.
*Remove* on the Downloads board only takes a job off the board (it stays in the Library);
*Remove* in the Library forgets the record. Neither ever deletes a media file.

## Audio formats

| Choice | What you get | When |
|---|---|---|
| MP3 320 / 192 / 128 | Transcoded MP3 with cover art and tags | Plays on anything. Can't beat the source (~130 kbps on YouTube) — 320 is about compatibility |
| M4A (AAC) | YouTube's AAC stream copied as-is, no re-encode | Apple Music, iPhones, cars |
| Best original | The site's best stream untouched: Opus from YouTube, MP3 from Bandcamp | Highest quality; Opus needs VLC or a modern player |

Every download gets `--embed-metadata --embed-thumbnail` (title, artist, album, date, cover).
Bandcamp supplies full album/track tags; for YouTube videos titled "Artist - Song" the two halves
become the artist and title tags when YouTube itself gives no artist. Entries chosen from a
playlist or album land in `<output>/<playlist name>/01 - Title.ext`.

## Layout

```
backend/app/main.py     FastAPI routes: /api/links, /api/jobs, /api/items, /api/library, /api/settings, /api/reveal
backend/app/links.py    normalise pasted links, classify video/playlist, site allowlist, error hints
backend/app/worker.py   the download queue: concurrency, progress, cancel, retry
backend/app/store.py    SQLite persistence for jobs, items and settings
backend/app/ytdlp.py    wrapper around the yt-dlp executable (probe, download, update, kill)
backend/app/formats.py  picks the sensible per-height options out of yt-dlp's format list
backend/app/desktop.py  open a folder / reveal a file in Finder or Explorer
backend/app/paths.py    app-data and default download folders
backend/tests/          pytest; fakes.py is a controllable stand-in for yt-dlp
backend/bin/            downloaded tools (gitignored)
frontend/src/           App.tsx, api.ts, components/ (form, jobs board, settings), lib/ + tests
scripts/fetch_binaries.py
PLAN.md                 the plan, decisions, and phase checklists
```

## Packaging

**Windows is built differently from macOS/Linux.** Windows Defender quarantines fresh, unsigned
PyInstaller executables as malware (a heuristic false positive that "dismiss" can't override), so
the Windows build has no custom `.exe` at all: `scripts/build_windows.py` assembles the
python.org *embeddable* runtime (its `pythonw.exe` is signed by the Python Software Foundation),
pip-installs the `app` package and dependencies next to it, adds `bin/`, and
`packaging/windows.iss` wraps that into a per-user Inno Setup installer whose Start-menu
shortcut runs `pythonw.exe -m app.launcher`. macOS and Linux use PyInstaller.

`app/launcher.py` is the desktop entry point: it picks a free localhost port, generates a
per-launch secret, starts uvicorn in-process and opens the browser at `/launch?token=…`, which
sets an `HttpOnly; SameSite=Strict` cookie and redirects to the app — so other websites can't
drive the API. A second launch finds the running copy via `instance.json` in the app-data folder.
Logs go to `app.log` there.

Build locally (any OS builds only for itself; CI builds all three):

```bash
(cd frontend && npm run build)             # -> backend/app/static
.venv/bin/pip install -e "backend[build]"  # adds PyInstaller
.venv/bin/python scripts/fetch_binaries.py
.venv/bin/pyinstaller --noconfirm packaging/MediaDownloader.spec   # -> dist/
.venv/bin/python scripts/bundle_binaries.py   # copies bin/ in untouched (PyInstaller would break yt-dlp)
```

Pushing a tag like `v0.4.0` runs `.github/workflows/release.yml`, which builds Windows, Linux
and (Intel) macOS bundles and attaches them to a GitHub Release here with the instructions from
`packaging/RELEASE_NOTES.md`. `workflow_dispatch` builds the artifacts without releasing.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MD_BIN_DIR` | `backend/bin` | where the helper binaries live |
| `MD_DATA_DIR` | per-OS app-data folder | where the jobs database lives |
| `MD_ALLOW_ANY_SITE` | unset | set to `1` to let yt-dlp try any site it supports (drops the allowlist) |
| `MD_TOKEN` / `MD_DESKTOP` | set by the launcher | launch secret and desktop-mode switch; leave unset in development |
| `MD_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | dev-server origins allowed to call the API |
| `VITE_API_URL` | *(empty)* | backend origin for the UI; empty = same origin / Vite proxy |

## Notes

- **Dubbed audio tracks.** YouTube serves many videos with the original soundtrack plus AI-dubbed
  ones, and the browser plays whichever matches *your* language. Settings → *Audio language*
  (default English) picks that track when it exists and the original otherwise; choose
  "Original (as uploaded)" to always get the original.
- **Vimeo needs you to be signed in** — even for public videos, at the moment. Set *Use cookies
  from* in Settings to a browser you're logged into Vimeo with (Firefox is the most reliable;
  Chrome on Windows usually refuses to share its cookies). The same setting unlocks private,
  age-restricted and members-only YouTube videos.
- **If YouTube stops working**, the first thing to try is updating yt-dlp:
  `backend/bin/yt-dlp/yt-dlp_macos -U` (or `yt-dlp_linux` / `yt-dlp.exe`). The desktop app will
  do this automatically on launch.
- Docker files were removed in Phase 0; a hosted/Docker mode is a later phase (see PLAN.md).
