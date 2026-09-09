export type ItemStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled';
export type Kind = 'video' | 'audio';
export type AudioBitrate = 128 | 192 | 320;

export interface Item {
  id: string;
  job_id: string;
  position: number;
  url: string;
  status: ItemStatus;
  title: string | null;
  uploader: string | null;
  duration: number | null;
  thumbnail: string | null;
  stage: string | null;
  downloaded: number | null;
  total: number | null;
  speed: number | null;
  eta: number | null;
  file_path: string | null;
  error: string | null;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  collection: string | null;
  collection_index: number | null;
}

export interface Job {
  id: string;
  created_at: number;
  archived: boolean;
  kind: Kind;
  options: {
    height?: number | null;
    subtitles?: boolean;
    audio_format?: AudioFormat;
    audio_bitrate?: number;
  };
  items: Item[];
}

export interface Settings {
  output_dir: string;
  concurrency: number;
  cookies_browser: string | null;
  /** Preferred audio track when a video has several (YouTube dubbing); "" = original. */
  audio_language: string;
  /** What the new-download form starts with (UI choice keys). */
  default_kind: Kind;
  default_video: string;
  default_audio: string;
}

export interface NewLink {
  url: string;
  title?: string | null;
  thumbnail?: string | null;
  /** Playlist/album the link came from - gets its own folder and "01 - " numbering. */
  collection?: string | null;
  collection_index?: number | null;
}

export type AudioFormat = 'mp3' | 'm4a' | 'best' | 'wav' | 'aiff';

export type JobCreate =
  | { links: NewLink[]; kind: 'video'; height: number | null; subtitles: boolean }
  | { links: NewLink[]; kind: 'audio'; audio_format: AudioFormat; audio_bitrate: AudioBitrate };

export interface LinkEntry {
  url: string;
  title: string | null;
  duration: number | null;
  thumbnail: string | null;
}

export interface LinkInfo {
  input: string;
  url: string;
  site: string;
  kind: 'video' | 'playlist';
  title?: string | null;
  thumbnail?: string | null;
  count?: number;
  truncated?: boolean;
  entries?: LinkEntry[];
}

export interface LinkProblem {
  input: string;
  message: string;
}

export interface InspectResult {
  links: LinkInfo[];
  errors: LinkProblem[];
}

const API_BASE = import.meta.env.VITE_API_URL ?? '';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** FastAPI puts a string in `detail` for our errors and a list of {msg} for validation errors. */
async function errorDetail(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    const detail = data.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((e: { msg?: string }) => (e.msg ?? '').replace(/^Value error, /, ''))
        .filter(Boolean)
        .join('; ');
    }
  } catch {
    // not JSON - fall through
  }
  return `Request failed (${res.status})`;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
  return (await res.json()) as T;
}

export const inspectLinks = (urls: string[]) =>
  request<InspectResult>('POST', '/api/links', { urls });
export const listJobs = () => request<Job[]>('GET', '/api/jobs');
export const createJob = (body: JobCreate) => request<Job>('POST', '/api/jobs', body);
export const cancelJob = (id: string) => request<{ ok: true }>('POST', `/api/jobs/${id}/cancel`);
export const deleteJob = (id: string) => request<{ ok: true }>('DELETE', `/api/jobs/${id}`);
export const cancelItem = (id: string) => request<{ ok: true }>('POST', `/api/items/${id}/cancel`);
export const retryItem = (id: string) => request<{ ok: true }>('POST', `/api/items/${id}/retry`);
export const getSettings = () => request<Settings>('GET', '/api/settings');
export const saveSettings = (body: Partial<Settings>) =>
  request<Settings>('PUT', '/api/settings', body);
/** Open a finished download in whatever the OS plays it with. */
export const openFile = (itemId: string) =>
  request<{ ok: true; path: string }>('POST', `/api/items/${itemId}/open`);
/** Show the downloads folder, one item's file, or a playlist's folder in the file manager. */
export const reveal = (itemId?: string, group?: string) =>
  request<{ ok: true; path: string }>('POST', '/api/reveal', {
    item_id: itemId ?? null,
    group: group ?? null,
  });

export interface LibraryItem extends Item {
  kind: Kind;
  options: Job['options'];
  /** Whether the file is still where the app put it. */
  exists: boolean;
}

export interface LibraryPage {
  items: LibraryItem[];
  total: number;
  offset: number;
  /** Playlists (collections): YouTube playlists, albums and user-made ones; each is a folder. */
  groups: string[];
}

export interface MoveResult {
  moved: number;
  skipped: { id: string; title: string | null; reason: string }[];
  /** The folder name as saved, or null for the main folder. */
  group: string | null;
}

export const getLibrary = (q: string, offset = 0, limit = 100, group: string | null = null) =>
  request<LibraryPage>(
    'GET',
    `/api/library?q=${encodeURIComponent(q)}&offset=${offset}&limit=${limit}` +
      (group === null ? '' : `&group=${encodeURIComponent(group)}`)
  );
export const removeDownloads = (itemIds: string[]) =>
  request<{ ok: true; removed: number }>('POST', '/api/library/remove', { item_ids: itemIds });
/** Move the files into a folder of that name (blank = the main folder) and group them there. */
export const moveDownloads = (itemIds: string[], group: string) =>
  request<MoveResult>('POST', '/api/library/move', { item_ids: itemIds, group });
export const redownload = (itemId: string) =>
  request<Job>('POST', `/api/library/${itemId}/redownload`);
export const forgetDownload = (itemId: string) =>
  request<{ ok: true }>('DELETE', `/api/library/${itemId}`);
export const clearFinished = () =>
  request<{ ok: true; archived: number }>('POST', '/api/jobs/clear-finished');

export interface Health {
  status: 'ok' | 'degraded';
  ytdlp: string | null;
  version: string;
  desktop: boolean;
  ytdlp_update: { state: 'idle' | 'running' | 'done' | 'failed'; message: string };
  app_update: { latest: string; url: string } | null;
  quit_requested: boolean;
  /** Set when the chosen browser's cookies can't be read and downloads run without them. */
  cookies_warning: string | null;
}

export const getHealth = () => request<Health>('GET', '/api/health');
export const updateYtdlp = () =>
  request<{ ok: true; message: string }>('POST', '/api/update-ytdlp');
export const quitApp = () => request<{ ok: true }>('POST', '/api/quit');

export const isActive = (status: ItemStatus) => status === 'queued' || status === 'running';
export const jobHasActive = (job: Job) => job.items.some((i) => isActive(i.status));
