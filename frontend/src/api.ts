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
}

export interface Job {
  id: string;
  created_at: number;
  kind: Kind;
  options: { height?: number | null; audio_format?: string; audio_bitrate?: number };
  items: Item[];
}

export interface Settings {
  output_dir: string;
  concurrency: number;
  cookies_browser: string | null;
}

export interface NewLink {
  url: string;
  title?: string | null;
  thumbnail?: string | null;
}

export type JobCreate =
  | { links: NewLink[]; kind: 'video'; height: number | null }
  | { links: NewLink[]; kind: 'audio'; audio_format: 'mp3'; audio_bitrate: AudioBitrate };

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
export const reveal = (itemId?: string) =>
  request<{ ok: true; path: string }>('POST', '/api/reveal', { item_id: itemId ?? null });

export const isActive = (status: ItemStatus) => status === 'queued' || status === 'running';
export const jobHasActive = (job: Job) => job.items.some((i) => isActive(i.status));
