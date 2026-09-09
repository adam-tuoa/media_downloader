import { useState, type ReactNode } from 'react';
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
import { compactInputClass as inputClass } from '../lib/ui';

const BROWSERS = [
  { value: 'firefox', label: 'Firefox' },
  { value: 'chrome', label: 'Chrome' },
  { value: 'edge', label: 'Edge' },
  { value: 'safari', label: 'Safari' },
  { value: 'brave', label: 'Brave' },
];

const noteClass = 'text-xs text-slate-500';
const buttonClass =
  'rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50';

function Field({
  id,
  label,
  sub = false,
  note,
  className = '',
  children,
}: {
  id: string;
  label: string;
  /** A smaller label, for choices grouped under a heading. */
  sub?: boolean;
  note?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`space-y-1 ${className}`}>
      <label
        htmlFor={id}
        className={
          sub ? 'block text-xs text-slate-600' : 'block text-sm font-medium text-slate-700'
        }
      >
        {label}
      </label>
      {children}
      {note && <p className={noteClass}>{note}</p>}
    </div>
  );
}

function Options({ items }: { items: { value: string | number; label: string }[] }) {
  return (
    <>
      {items.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </>
  );
}

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
    <div className="grid gap-4 sm:grid-cols-2">
      <Field id="folder" label="Save downloads to" className="sm:col-span-2">
        <div className="flex gap-2">
          <input
            id="folder"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
            className={inputClass}
            spellCheck={false}
          />
          <button type="button" onClick={() => open.mutate()} className={`shrink-0 ${buttonClass}`}>
            Open folder
          </button>
        </div>
      </Field>

      <fieldset className="space-y-2 rounded-md border border-slate-200 p-3 sm:col-span-2">
        <legend className="px-1 text-sm font-medium text-slate-700">
          New downloads start with
        </legend>
        <div className="grid gap-3 sm:grid-cols-4">
          <Field id="default-kind" label="Video or audio" sub>
            <select
              id="default-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as Kind)}
              className={inputClass}
            >
              <option value="video">Video</option>
              <option value="audio">Audio</option>
            </select>
          </Field>
          <Field id="default-video" label="Video quality" sub>
            <select
              id="default-video"
              value={video}
              onChange={(e) => setVideo(e.target.value)}
              className={inputClass}
            >
              <Options items={VIDEO_QUALITIES} />
            </select>
          </Field>
          <Field id="default-audio" label="Audio format" sub className="sm:col-span-2">
            <select
              id="default-audio"
              value={audio}
              onChange={(e) => setAudio(e.target.value)}
              className={inputClass}
            >
              <Options items={AUDIO_CHOICES} />
            </select>
          </Field>
        </div>
        <p className={noteClass}>You can still change these for any download.</p>
      </fieldset>

      <Field
        id="language"
        label="Language"
        note="For YouTube’s dubbed audio tracks and for subtitles. You get this language when the video has it, otherwise the original."
      >
        <select
          id="language"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className={inputClass}
        >
          <Options items={LANGUAGES} />
        </select>
      </Field>

      <Field
        id="cookies"
        label="Use cookies from"
        note="Only for videos that need a sign-in — Vimeo, private or members-only. Pick a browser you’re signed in with; Firefox works best. Safari needs Media Downloader allowed under System Settings → Privacy & Security → Full Disk Access. Chrome on Windows often won’t share its cookies."
      >
        <select
          id="cookies"
          value={cookies}
          onChange={(e) => setCookies(e.target.value)}
          className={inputClass}
        >
          <option value="">No browser (default)</option>
          <Options items={BROWSERS} />
        </select>
      </Field>

      <Field id="concurrency" label="Downloads at the same time">
        <select
          id="concurrency"
          value={concurrency}
          onChange={(e) => setConcurrency(Number(e.target.value))}
          className={inputClass}
        >
          <Options items={[1, 2, 3, 4].map((n) => ({ value: n, label: String(n) }))} />
        </select>
      </Field>

      <div className="flex items-end justify-end gap-3">
        {save.isSuccess && !dirty && <span className="text-sm text-green-700">Saved</span>}
        {save.error && (
          <span role="alert" className="text-sm text-red-700">
            {save.error.message}
          </span>
        )}
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
          className="rounded-md bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
        >
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
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
    <div className="space-y-1 border-t border-slate-100 pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-slate-700">
          Downloader engine (yt-dlp){health.data?.ytdlp ? ` · ${health.data.ytdlp}` : ''}
        </p>
        <div className="flex items-center gap-3">
          {update.data && <span className="text-sm text-green-700">{update.data.message}</span>}
          {update.error && (
            <span role="alert" className="text-sm text-red-700">
              {update.error.message}
            </span>
          )}
          <button
            type="button"
            disabled={running}
            onClick={() => update.mutate()}
            className={buttonClass}
          >
            {running ? 'Updating…' : 'Update now'}
          </button>
        </div>
      </div>
      <p className={noteClass}>
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
