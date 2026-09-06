import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createJob, type AudioBitrate, type JobCreate, type Kind } from '../api';
import { parseLinks } from '../lib/links';
import { inputClass, segmentClass } from '../lib/ui';

const VIDEO_QUALITIES: { value: string; label: string; height: number | null }[] = [
  { value: 'best', label: 'Best available', height: null },
  { value: '1080', label: '1080p', height: 1080 },
  { value: '720', label: '720p', height: 720 },
  { value: '480', label: '480p', height: 480 },
  { value: '360', label: '360p (small)', height: 360 },
];
const BITRATES: AudioBitrate[] = [320, 192, 128];

export default function NewJobForm() {
  const queryClient = useQueryClient();
  const [text, setText] = useState('');
  const [kind, setKind] = useState<Kind>('video');
  const [quality, setQuality] = useState('best');
  const [bitrate, setBitrate] = useState<AudioBitrate>(320);

  const create = useMutation({
    mutationFn: createJob,
    onSuccess: () => {
      setText('');
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });

  const links = parseLinks(text);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!links.length) return;
    const body: JobCreate =
      kind === 'video'
        ? {
            urls: links,
            kind,
            height: VIDEO_QUALITIES.find((q) => q.value === quality)?.height ?? null,
          }
        : { urls: links, kind, audio_format: 'mp3', audio_bitrate: bitrate };
    create.mutate(body);
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded-xl bg-white p-5 shadow-md sm:p-6">
      <div className="space-y-2">
        <label htmlFor="links" className="block text-sm font-medium text-slate-700">
          Paste one or more links, one per line
        </label>
        <textarea
          id="links"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={'https://www.youtube.com/watch?v=...\nhttps://youtu.be/...'}
          rows={3}
          className={`${inputClass} resize-y font-mono text-sm`}
          autoFocus
        />
      </div>

      <div className="flex gap-2 rounded-lg bg-slate-100 p-1">
        <button
          type="button"
          className={segmentClass(kind === 'video')}
          onClick={() => setKind('video')}
        >
          Video
        </button>
        <button
          type="button"
          className={segmentClass(kind === 'audio')}
          onClick={() => setKind('audio')}
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
            value={quality}
            onChange={(e) => setQuality(e.target.value)}
            className={inputClass}
          >
            {VIDEO_QUALITIES.map((q) => (
              <option key={q.value} value={q.value}>
                {q.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-500">
            If a video isn’t available at that size, you get the next one down.
          </p>
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
            className={inputClass}
          >
            {BITRATES.map((b) => (
              <option key={b} value={b}>
                {b} kbps{b === 320 ? ' — plays everywhere' : ''}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-500">
            An MP3 can’t sound better than the original (usually about 130 kbps), whichever number
            you pick.
          </p>
        </div>
      )}

      <button
        type="submit"
        disabled={!links.length || create.isPending}
        className="w-full rounded-md bg-green-600 p-3 text-base font-semibold text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:bg-green-300"
      >
        {create.isPending
          ? 'Adding…'
          : links.length > 1
            ? `Download ${links.length} links`
            : 'Download'}
      </button>

      {create.error && (
        <p role="alert" className="rounded-md bg-red-100 p-3 text-red-800">
          {create.error.message}
        </p>
      )}
    </form>
  );
}
