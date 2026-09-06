import { useState, type FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { download, probe, type AudioBitrate, type DownloadRequest } from './api';
import { formatDuration } from './lib/format';

type Kind = 'video' | 'audio';
const BITRATES: AudioBitrate[] = [320, 192, 128];

const inputClass =
  'w-full rounded-md border border-slate-300 bg-white p-3 text-base focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200';
const selectClass = inputClass;

function segment(active: boolean): string {
  return `flex-1 rounded-md px-4 py-3 text-base font-medium transition ${
    active ? 'bg-blue-600 text-white shadow' : 'bg-white text-slate-700 hover:bg-slate-50'
  }`;
}

export default function App() {
  const [url, setUrl] = useState('');
  const [kind, setKind] = useState<Kind>('video');
  const [height, setHeight] = useState<number | null>(null);
  const [bitrate, setBitrate] = useState<AudioBitrate>(320);

  const probeM = useMutation({
    mutationFn: probe,
    onSuccess: (info) => {
      setHeight(info.video[0]?.height ?? null);
      setKind(info.video.length ? 'video' : 'audio');
    },
  });
  const downloadM = useMutation({ mutationFn: download });

  const info = probeM.data;
  const probedUrl = probeM.variables;
  const busy = probeM.isPending || downloadM.isPending;
  const error = probeM.error ?? downloadM.error;

  const onCheck = (e: FormEvent) => {
    e.preventDefault();
    downloadM.reset();
    probeM.mutate(url.trim());
  };

  const onDownload = () => {
    if (!info || !probedUrl) return;
    const req: DownloadRequest =
      kind === 'video'
        ? { url: probedUrl, kind, height }
        : { url: probedUrl, kind, audio_format: 'mp3', audio_bitrate: bitrate };
    downloadM.mutate(req);
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center p-4">
      <div className="rounded-xl bg-white p-6 shadow-md sm:p-8">
        <h1 className="mb-6 text-center text-3xl font-bold">Media Downloader</h1>

        <form onSubmit={onCheck} className="space-y-3">
          <label htmlFor="url" className="block text-sm font-medium text-slate-700">
            Paste a YouTube link
          </label>
          <input
            id="url"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
            className={inputClass}
            autoFocus
            required
          />
          <button
            type="submit"
            disabled={busy || !url.trim()}
            className="w-full rounded-md bg-blue-600 p-3 text-base font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            {probeM.isPending ? 'Checking…' : 'Check link'}
          </button>
        </form>

        {info && (
          <section className="mt-6 space-y-5">
            <div className="flex items-start gap-4">
              {info.thumbnail && (
                <img
                  src={info.thumbnail}
                  alt=""
                  className="w-40 shrink-0 rounded-md object-cover"
                />
              )}
              <div className="min-w-0">
                <h2 className="text-lg font-semibold leading-snug">{info.title}</h2>
                <p className="mt-1 text-sm text-slate-600">
                  {[info.uploader, formatDuration(info.duration)].filter(Boolean).join(' · ')}
                </p>
              </div>
            </div>

            <div className="flex gap-2 rounded-lg bg-slate-100 p-1">
              <button
                type="button"
                className={segment(kind === 'video')}
                onClick={() => setKind('video')}
                disabled={!info.video.length}
              >
                Video
              </button>
              <button
                type="button"
                className={segment(kind === 'audio')}
                onClick={() => setKind('audio')}
                disabled={!info.audio}
              >
                Audio (MP3)
              </button>
            </div>

            {kind === 'video' ? (
              <div className="space-y-2">
                <label htmlFor="quality" className="block text-sm font-medium text-slate-700">
                  Quality
                </label>
                <select
                  id="quality"
                  value={height ?? ''}
                  onChange={(e) => setHeight(Number(e.target.value))}
                  className={selectClass}
                >
                  {info.video.map((o) => (
                    <option key={o.format_id} value={o.height}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="space-y-2">
                <label htmlFor="bitrate" className="block text-sm font-medium text-slate-700">
                  MP3 quality
                </label>
                <select
                  id="bitrate"
                  value={bitrate}
                  onChange={(e) => setBitrate(Number(e.target.value) as AudioBitrate)}
                  className={selectClass}
                >
                  {BITRATES.map((b) => (
                    <option key={b} value={b}>
                      {b} kbps{b === 320 ? ' — plays everywhere' : ''}
                    </option>
                  ))}
                </select>
                {info.audio?.abr && (
                  <p className="text-xs text-slate-500">
                    The original audio is about {info.audio.abr} kbps; an MP3 can’t sound better
                    than that, whichever number you pick.
                  </p>
                )}
              </div>
            )}

            <button
              type="button"
              onClick={onDownload}
              disabled={busy}
              className="w-full rounded-md bg-green-600 p-3 text-base font-semibold text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:bg-green-300"
            >
              {downloadM.isPending ? 'Preparing your file… this can take a minute' : 'Download'}
            </button>
          </section>
        )}

        {downloadM.isSuccess && (
          <p className="mt-4 rounded-md bg-green-100 p-3 text-green-800">
            Saved: {downloadM.data}
          </p>
        )}
        {error && (
          <p role="alert" className="mt-4 rounded-md bg-red-100 p-3 text-red-800">
            {error.message}
          </p>
        )}
      </div>
    </main>
  );
}
