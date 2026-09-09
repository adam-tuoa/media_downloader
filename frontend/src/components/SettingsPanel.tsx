import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getHealth,
  getSettings,
  reveal,
  saveSettings,
  updateYtdlp,
  type Kind,
  type Settings,
} from '../api';
import {
  AUDIO_CHOICES,
  LANGUAGES,
  VIDEO_QUALITIES,
  audioChoice,
  videoQuality,
} from '../lib/options';
import { inputClass } from '../lib/ui';

const BROWSERS = [
  { value: 'firefox', label: 'Firefox' },
  { value: 'chrome', label: 'Chrome' },
  { value: 'edge', label: 'Edge' },
  { value: 'safari', label: 'Safari' },
  { value: 'brave', label: 'Brave' },
];

function SettingsForm({ initial }: { initial: Settings }) {
  const queryClient = useQueryClient();
  const [folder, setFolder] = useState(initial.output_dir);
  const [concurrency, setConcurrency] = useState(initial.concurrency);
  const [cookies, setCookies] = useState(initial.cookies_browser ?? '');
  const [language, setLanguage] = useState(initial.audio_language ?? 'en');
  const [kind, setKind] = useState<Kind>(initial.default_kind === 'audio' ? 'audio' : 'video');
  const [video, setVideo] = useState(videoQuality(initial.default_video));
  const [audio, setAudio] = useState(audioChoice(initial.default_audio ?? '').value);

  const save = useMutation({
    mutationFn: saveSettings,
    onSuccess: (data) => queryClient.setQueryData(['settings'], data),
  });
  const open = useMutation({ mutationFn: () => reveal() });

  const dirty =
    folder !== initial.output_dir ||
    concurrency !== initial.concurrency ||
    cookies !== (initial.cookies_browser ?? '') ||
    language !== (initial.audio_language ?? 'en') ||
    kind !== (initial.default_kind === 'audio' ? 'audio' : 'video') ||
    video !== videoQuality(initial.default_video) ||
    audio !== audioChoice(initial.default_audio ?? '').value;

  return (
    <>
      <div className="space-y-2">
        <label htmlFor="folder" className="block text-sm font-medium text-slate-700">
          Save downloads to
        </label>
        <div className="flex gap-2">
          <input
            id="folder"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            className={inputClass}
            spellCheck={false}
          />
          <button
            type="button"
            onClick={() => open.mutate()}
            className="shrink-0 rounded-md border border-slate-300 px-4 text-sm font-medium hover:bg-slate-50"
          >
            Open folder
          </button>
        </div>
      </div>

      <fieldset className="space-y-3 rounded-md border border-slate-200 p-3">
        <legend className="px-1 text-sm font-medium text-slate-700">
          New downloads start with
        </legend>
        <div className="space-y-1">
          <label htmlFor="default-kind" className="block text-xs text-slate-600">
            Video or audio
          </label>
          <select
            id="default-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as Kind)}
            className={inputClass}
          >
            <option value="video">Video</option>
            <option value="audio">Audio</option>
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="default-video" className="block text-xs text-slate-600">
            Video quality
          </label>
          <select
            id="default-video"
            value={video}
            onChange={(e) => setVideo(e.target.value)}
            className={inputClass}
          >
            {VIDEO_QUALITIES.map((q) => (
              <option key={q.value} value={q.value}>
                {q.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="default-audio" className="block text-xs text-slate-600">
            Audio format
          </label>
          <select
            id="default-audio"
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
        </div>
        <p className="text-xs text-slate-500">You can still change these for any download.</p>
      </fieldset>

      <div className="space-y-2">
        <label htmlFor="concurrency" className="block text-sm font-medium text-slate-700">
          Downloads at the same time
        </label>
        <select
          id="concurrency"
          value={concurrency}
          onChange={(e) => setConcurrency(Number(e.target.value))}
          className={inputClass}
        >
          {[1, 2, 3, 4].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <label htmlFor="language" className="block text-sm font-medium text-slate-700">
          Language
        </label>
        <select
          id="language"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className={inputClass}
        >
          {LANGUAGES.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
        <p className="text-xs text-slate-500">
          Used for YouTube’s dubbed audio tracks and for subtitles. You get this language when the
          video has it, otherwise the original.
        </p>
      </div>

      <div className="space-y-2">
        <label htmlFor="cookies" className="block text-sm font-medium text-slate-700">
          Use cookies from
        </label>
        <select
          id="cookies"
          value={cookies}
          onChange={(e) => setCookies(e.target.value)}
          className={inputClass}
        >
          <option value="">No browser (default)</option>
          {BROWSERS.map((b) => (
            <option key={b.value} value={b.value}>
              {b.label}
            </option>
          ))}
        </select>
        <p className="text-xs text-slate-500">
          Only needed for videos that require being signed in — Vimeo, private or members-only
          videos. Pick a browser you’re signed in with. Firefox works best. Safari needs Media
          Downloader switched on under System Settings → Privacy &amp; Security → Full Disk Access.
          Chrome on Windows often won’t share its cookies.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={() =>
            save.mutate({
              output_dir: folder,
              concurrency,
              cookies_browser: cookies,
              audio_language: language,
              default_kind: kind,
              default_video: video,
              default_audio: audio,
            })
          }
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
        >
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
        {save.isSuccess && !dirty && <span className="text-sm text-green-700">Saved</span>}
        {save.error && (
          <span role="alert" className="text-sm text-red-700">
            {save.error.message}
          </span>
        )}
      </div>
    </>
  );
}

function EngineUpdate() {
  const queryClient = useQueryClient();
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth });
  const update = useMutation({
    mutationFn: updateYtdlp,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['health'] }),
  });
  const running = health.data?.ytdlp_update?.state === 'running' || update.isPending;
  return (
    <div className="space-y-2 border-t border-slate-100 pt-4">
      <p className="text-sm font-medium text-slate-700">
        Downloader engine (yt-dlp){health.data?.ytdlp ? ` · ${health.data.ytdlp}` : ''}
      </p>
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={running}
          onClick={() => update.mutate()}
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? 'Updating…' : 'Update now'}
        </button>
        {update.data && <span className="text-sm text-green-700">{update.data.message}</span>}
        {update.error && (
          <span role="alert" className="text-sm text-red-700">
            {update.error.message}
          </span>
        )}
      </div>
      <p className="text-xs text-slate-500">
        If YouTube suddenly stops working, this is the first thing to try. The app also checks on
        every launch.
      </p>
    </div>
  );
}

export default function SettingsPanel() {
  const settings = useQuery({ queryKey: ['settings'], queryFn: getSettings });

  return (
    <div className="space-y-4">
      {settings.data ? (
        // Keyed on the saved values so the form resets to them after a save or refetch.
        <SettingsForm
          key={[
            settings.data.output_dir,
            settings.data.concurrency,
            settings.data.cookies_browser ?? '',
            settings.data.audio_language,
            settings.data.default_kind,
            settings.data.default_video,
            settings.data.default_audio,
          ].join('|')}
          initial={settings.data}
        />
      ) : settings.error ? (
        <p role="alert" className="text-sm text-red-700">
          {settings.error.message}
        </p>
      ) : (
        <p className="text-sm text-slate-500">Loading…</p>
      )}
      <EngineUpdate />
    </div>
  );
}
