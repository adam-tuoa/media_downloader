# Media Downloader

A small, friendly downloader for YouTube (Vimeo and Bandcamp coming) built on
[yt-dlp](https://github.com/yt-dlp/yt-dlp). Paste a link, pick **Video** at a quality or
**Audio (MP3)**, get the file. Heading towards a double-click desktop app that batch-downloads
lists of links — see [PLAN.md](PLAN.md) for where this is going and what's done.

**Status:** Phase 1 complete — paste one or more links, choose Video (quality) or Audio (MP3),
watch per-item progress, files land in a folder of your choice. Playlists, batch niceties and
better audio formats are next (Phases 2–3).

## Stack

- **Backend:** Python 3.13, FastAPI, driving the official `yt-dlp` executable (not the library —
  the executable self-updates, which matters because YouTube changes constantly)
- **Frontend:** React 19, TypeScript, Vite, Tailwind v4, TanStack Query
- **Bundled tools:** `yt-dlp`, `ffmpeg`/`ffprobe`, `deno` (yt-dlp needs a JavaScript runtime to
  solve YouTube's challenges) — downloaded into `backend/bin/` by a script, never committed

## Setup

Requirements: Python 3.13, Node 24 (or 22+), git. No system ffmpeg needed — it's fetched.

```bash
# 1. Python environment
python3.13 -m venv .venv
.venv/bin/pip install -e "backend[dev]"

# 2. Helper binaries (~350 MB, once). The first yt-dlp launch is slow on macOS while the OS
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

git clone https://github.com/adam-tuoa/youtube_downloader_app.git
cd youtube_downloader_app
py -3 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -e "backend[dev]"
.venv\Scripts\python scripts\fetch_binaries.py     # ~250 MB; Defender may pause on yt-dlp.exe once
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

Submitting links creates a **job** with one **item** per link. A worker inside the API process
takes queued items (two at a time by default), probes each with yt-dlp, downloads it into
`<output folder>/.incomplete/<item id>/`, and moves the finished file into the output folder
(never overwriting — a duplicate gets ` (1)` appended). Progress goes into a SQLite database that
the UI polls once a second while anything is active. Interrupted items are re-queued on restart.

| What | Where |
|---|---|
| Jobs database | macOS `~/Library/Application Support/MediaDownloader/`, Windows `%LOCALAPPDATA%\MediaDownloader\`, Linux `~/.local/share/MediaDownloader/` — override with `MD_DATA_DIR` |
| Downloads (default) | `<your Downloads folder>/Media Downloader/` — change it in Settings |

## Layout

```
backend/app/main.py     FastAPI routes: /api/jobs, /api/items, /api/settings, /api/reveal, /api/probe
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

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MD_BIN_DIR` | `backend/bin` | where the helper binaries live |
| `MD_DATA_DIR` | per-OS app-data folder | where the jobs database lives |
| `MD_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | dev-server origins allowed to call the API |
| `VITE_API_URL` | *(empty)* | backend origin for the UI; empty = same origin / Vite proxy |

## Notes

- **If YouTube stops working**, the first thing to try is updating yt-dlp:
  `backend/bin/yt-dlp/yt-dlp_macos -U` (or `yt-dlp_linux` / `yt-dlp.exe`). The desktop app will
  do this automatically on launch.
- Docker files were removed in Phase 0; a hosted/Docker mode is a later phase (see PLAN.md).
