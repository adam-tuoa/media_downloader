import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  createJob,
  inspectLinks,
  type InspectResult,
  type JobCreate,
  type Kind,
  type NewLink,
} from '../api';
import { allEntryUrls, collectLinks, needsReview, parseLinks } from '../lib/links';
import {
  AUDIO_CHOICES,
  DEFAULT_AUDIO_CHOICE,
  VIDEO_QUALITIES,
  audioChoice,
  videoHeight,
} from '../lib/options';
import { inputClass, segmentClass } from '../lib/ui';
import ReviewPanel from './ReviewPanel';

export default function NewJobForm() {
  const queryClient = useQueryClient();
  const [text, setText] = useState('');
  const [kind, setKind] = useState<Kind>('video');
  const [quality, setQuality] = useState('best');
  const [subtitles, setSubtitles] = useState(false);
  const [audio, setAudio] = useState(DEFAULT_AUDIO_CHOICE);
  const [review, setReview] = useState<InspectResult | null>(null);

  const create = useMutation({
    mutationFn: createJob,
    onSuccess: () => {
      setText('');
      setReview(null);
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });

  const buildJob = (chosen: NewLink[]): JobCreate => {
    if (kind === 'video') return { links: chosen, kind, height: videoHeight(quality), subtitles };
    const choice = audioChoice(audio);
    return {
      links: chosen,
      kind,
      audio_format: choice.format,
      audio_bitrate: choice.bitrate ?? 320,
    };
  };

  // Step one: ask the backend what each line is. Plain videos go straight to the queue;
  // playlists or problems get a review step first.
  const inspect = useMutation({
    mutationFn: inspectLinks,
    onSuccess: (result) => {
      if (needsReview(result)) setReview(result);
      else create.mutate(buildJob(collectLinks(result, allEntryUrls(result))));
    },
  });

  const links = parseLinks(text);
  const busy = inspect.isPending || create.isPending;
  const error = inspect.error ?? create.error;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (links.length) inspect.mutate(links);
  };

  if (review) {
    return (
      <div className="rounded-xl bg-white p-5 shadow-md sm:p-6">
        <ReviewPanel
          result={review}
          busy={create.isPending}
          onConfirm={(chosen) => create.mutate(buildJob(chosen))}
          onBack={() => setReview(null)}
        />
        {create.error && (
          <p role="alert" className="mt-4 rounded-md bg-red-100 p-3 text-red-800">
            {create.error.message}
          </p>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4 rounded-xl bg-white p-5 shadow-md sm:p-6">
      <div className="space-y-2">
        <label htmlFor="links" className="block text-sm font-medium text-slate-700">
          Paste links — videos, playlists or albums — one per line
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
          <label className="flex items-center gap-2 pt-1 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={subtitles}
              onChange={(e) => setSubtitles(e.target.checked)}
              className="h-4 w-4"
            />
            Include English subtitles when the video has them
          </label>
        </div>
      ) : (
        <div className="space-y-2">
          <label htmlFor="audio" className="block text-sm font-medium text-slate-700">
            Audio format
          </label>
          <select
            id="audio"
            value={audio}
            onChange={(e) => setAudio(e.target.value)}
            className={inputClass}
          >
            {AUDIO_CHOICES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-slate-500">{audioChoice(audio).note}</p>
          <p className="text-xs text-slate-500">
            Cover art and title/artist/album tags are always added. Playlists and albums go into
            their own folder, numbered.
          </p>
        </div>
      )}

      <button
        type="submit"
        disabled={!links.length || busy}
        className="w-full rounded-md bg-green-600 p-3 text-base font-semibold text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:bg-green-300"
      >
        {inspect.isPending
          ? 'Checking links…'
          : create.isPending
            ? 'Adding…'
            : links.length > 1
              ? `Download ${links.length} links`
              : 'Download'}
      </button>

      {error && (
        <p role="alert" className="rounded-md bg-red-100 p-3 text-red-800">
          {error.message}
        </p>
      )}
    </form>
  );
}
