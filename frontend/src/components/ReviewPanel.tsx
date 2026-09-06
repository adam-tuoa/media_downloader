import { useState } from 'react';
import type { InspectResult, NewLink } from '../api';
import { formatDuration } from '../lib/format';
import { allEntryUrls, collectLinks, playlistLabel } from '../lib/links';

interface Props {
  result: InspectResult;
  busy: boolean;
  onConfirm: (links: NewLink[]) => void;
  onBack: () => void;
}

export default function ReviewPanel({ result, busy, onConfirm, onBack }: Props) {
  const [selected, setSelected] = useState<Set<string>>(() => allEntryUrls(result));
  const chosen = collectLinks(result, selected);

  const toggle = (url: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  const setAll = (urls: string[], on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      for (const u of urls) {
        if (on) next.add(u);
        else next.delete(u);
      }
      return next;
    });

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Check what to download</h2>

      {result.errors.length > 0 && (
        <ul className="space-y-1 rounded-md bg-red-50 p-3 text-sm text-red-800">
          {result.errors.map((e, i) => (
            <li key={i}>
              <span className="font-mono text-xs text-red-600">{e.input}</span>
              <br />
              {e.message}
            </li>
          ))}
        </ul>
      )}

      {result.links.map((link) =>
        link.kind === 'video' ? (
          <div key={link.url} className="flex items-center gap-2 text-sm">
            <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-800">
              Video
            </span>
            <span className="truncate">{link.title ?? link.url}</span>
          </div>
        ) : (
          <section key={link.url} className="rounded-md border border-slate-200">
            <header className="flex flex-wrap items-center justify-between gap-2 bg-slate-50 px-3 py-2">
              <div className="min-w-0">
                <span className="mr-2 rounded bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-800">
                  Playlist
                </span>
                <span className="font-medium">{link.title ?? link.url}</span>
                <span className="ml-2 text-sm text-slate-500">{playlistLabel(link)}</span>
              </div>
              <div className="flex gap-3 text-sm">
                <button
                  type="button"
                  className="text-blue-700 underline"
                  onClick={() =>
                    setAll(
                      (link.entries ?? []).map((e) => e.url),
                      true
                    )
                  }
                >
                  All
                </button>
                <button
                  type="button"
                  className="text-blue-700 underline"
                  onClick={() =>
                    setAll(
                      (link.entries ?? []).map((e) => e.url),
                      false
                    )
                  }
                >
                  None
                </button>
              </div>
            </header>
            <ul className="max-h-72 divide-y divide-slate-100 overflow-y-auto">
              {(link.entries ?? []).map((e, i) => (
                <li key={e.url}>
                  <label className="flex cursor-pointer items-center gap-3 px-3 py-2 text-sm hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={selected.has(e.url)}
                      onChange={() => toggle(e.url)}
                      className="h-4 w-4"
                    />
                    <span className="w-6 text-right text-slate-400">{i + 1}</span>
                    <span className="min-w-0 flex-1 truncate">{e.title ?? e.url}</span>
                    <span className="text-slate-500">{formatDuration(e.duration)}</span>
                  </label>
                </li>
              ))}
            </ul>
          </section>
        )
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={!chosen.length || busy}
          onClick={() => onConfirm(chosen)}
          className="rounded-md bg-green-600 px-4 py-3 text-base font-semibold text-white hover:bg-green-700 disabled:cursor-not-allowed disabled:bg-green-300"
        >
          {busy ? 'Adding…' : `Download ${chosen.length} ${chosen.length === 1 ? 'item' : 'items'}`}
        </button>
        <button type="button" onClick={onBack} className="text-sm text-slate-600 underline">
          Back
        </button>
      </div>
    </div>
  );
}
