export interface VideoOption {
  height: number;
  fps: number | null;
  vcodec: string;
  ext: string;
  format_id: string;
  audio_format_id: string | null;
  filesize: number | null;
  label: string;
}

export interface AudioOption {
  format_id: string;
  abr: number | null;
  acodec: string;
  ext: string;
  filesize: number | null;
}

export interface ProbeResult {
  id: string;
  title: string;
  uploader: string | null;
  duration: number | null;
  thumbnail: string | null;
  webpage_url: string;
  extractor: string;
  video: VideoOption[];
  audio: AudioOption | null;
}

export type AudioBitrate = 128 | 192 | 320;

export type DownloadRequest =
  | { url: string; kind: 'video'; height: number | null }
  | { url: string; kind: 'audio'; audio_format: 'mp3'; audio_bitrate: AudioBitrate };

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

async function post(path: string, body: unknown): Promise<Response> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(await errorDetail(res), res.status);
  return res;
}

export async function probe(url: string): Promise<ProbeResult> {
  return (await post('/api/probe', { url })).json();
}

/** Downloads through the browser; resolves with the saved filename. */
export async function download(req: DownloadRequest): Promise<string> {
  const res = await post('/api/download', req);
  const filename = filenameFrom(res.headers.get('Content-Disposition')) ?? 'download';
  saveBlob(await res.blob(), filename);
  return filename;
}

export function filenameFrom(header: string | null): string | null {
  if (!header) return null;
  const star = header.match(/filename\*=utf-8''([^;]+)/i);
  if (star) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      // malformed encoding - try the plain form
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/);
  return plain ? plain[1] : null;
}

function saveBlob(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
