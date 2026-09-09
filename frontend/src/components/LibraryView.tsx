import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { forgetDownload, getLibrary, redownload, reveal, type LibraryItem } from '../api';
import { baseName, formatDuration, formatWhen } from '../lib/format';
import { describeJob } from '../lib/items';
import { inputClass } from '../lib/ui';

const PAGE = 100;

function LibraryRow({ item, onRequeued }: { item: LibraryItem; onRequeued: () => void }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['library'] });
  const again = useMutation({
    mutationFn: redownload,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      onRequeued();
    },
  });
  const forget = useMutation({ mutationFn: forgetDownload, onSuccess: refresh });
  const show = useMutation({ mutationFn: reveal });

  const what = describeJob({
    id: '',
    created_at: 0,
    archived: false,
    kind: item.kind,
    options: item.options,
    items: [],
  });
  const meta = [
    what,
    item.collection
      ? `${item.collection}${item.collection_index ? ` · #${item.collection_index}` : ''}`
      : null,
    item.duration ? formatDuration(item.duration) : null,
    item.finished_at ? formatWhen(item.finished_at) : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <li className="flex items-start gap-3 py-3">
      <div className="h-12 w-20 shrink-0 overflow-hidden rounded bg-slate-200">
        {item.thumbnail && (
          <img src={item.thumbnail} alt="" className="h-full w-full object-cover" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium" title={item.title ?? item.url}>
          {item.title ?? item.url}
        </p>
        <p className="truncate text-sm text-slate-600" title={meta}>
          {meta}
        </p>
        <p
          className={`truncate text-xs ${item.exists ? 'text-slate-500' : 'text-amber-700'}`}
          title={item.file_path ?? ''}
        >
          {item.exists
            ? baseName(item.file_path)
            : `File missing — was ${baseName(item.file_path)}`}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1 text-sm">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
            item.exists ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'
          }`}
        >
          {item.exists ? 'On disk' : 'Missing'}
        </span>
        {item.exists && (
          <button
            type="button"
            onClick={() => show.mutate(item.id)}
            className="text-blue-700 underline"
          >
            Show file
          </button>
        )}
        <button
          type="button"
          onClick={() => again.mutate(item.id)}
          disabled={again.isPending}
          className="text-blue-700 underline disabled:opacity-50"
        >
          Download again
        </button>
        <button
          type="button"
          onClick={() => {
            if (window.confirm('Remove this from the history? The file itself is not touched.'))
              forget.mutate(item.id);
          }}
          className="text-slate-500 underline hover:text-slate-800"
        >
          Remove
        </button>
      </div>
    </li>
  );
}

export default function LibraryView({ onRequeued }: { onRequeued: () => void }) {
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(PAGE);
  const library = useQuery({
    queryKey: ['library', query, limit],
    queryFn: () => getLibrary(query, 0, limit),
    placeholderData: (previous) => previous,
  });

  return (
    <section className="space-y-4 rounded-xl bg-white p-5 shadow-md sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">Library</h2>
        {library.data && (
          <span className="text-sm text-slate-500">
            {library.data.total} {library.data.total === 1 ? 'download' : 'downloads'}
            {query ? ' matching' : ''}
          </span>
        )}
      </div>
      <input
        type="search"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setLimit(PAGE);
        }}
        placeholder="Search titles, albums, links…"
        className={inputClass}
        aria-label="Search the library"
      />
      {library.isPending ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : library.error ? (
        <p role="alert" className="rounded-md bg-red-100 p-3 text-red-800">
          {library.error.message}
        </p>
      ) : library.data.items.length === 0 ? (
        <p className="text-center text-slate-500">
          {query ? 'Nothing matches that.' : 'Nothing downloaded yet.'}
        </p>
      ) : (
        <>
          <ul className="divide-y divide-slate-100">
            {library.data.items.map((item) => (
              <LibraryRow key={item.id} item={item} onRequeued={onRequeued} />
            ))}
          </ul>
          {library.data.items.length < library.data.total && (
            <button
              type="button"
              onClick={() => setLimit((n) => n + PAGE)}
              className="w-full rounded-md border border-slate-300 py-2 text-sm font-medium hover:bg-slate-50"
            >
              Show more ({library.data.total - library.data.items.length} left)
            </button>
          )}
        </>
      )}
    </section>
  );
}
