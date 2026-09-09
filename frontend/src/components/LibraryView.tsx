import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderInput, FolderOpen, Play, RotateCw, Trash2, X } from 'lucide-react';
import {
  forgetDownload,
  getLibrary,
  moveDownloads,
  redownload,
  removeDownloads,
  reveal,
  type LibraryItem,
} from '../api';
import { baseName, formatDuration, formatWhen } from '../lib/format';
import { describeJob, describeMove } from '../lib/items';
import { useOpenFile } from '../lib/openFile';
import { inputClass } from '../lib/ui';
import ActionButton from './ActionButton';
import { Thumbnail, Title } from './FileLink';
import IconButton from './IconButton';
import Modal from './Modal';

const PAGE = 100;

function LibraryRow({
  item,
  selected,
  onSelect,
  onRequeued,
}: {
  item: LibraryItem;
  selected: boolean;
  onSelect: (on: boolean) => void;
  onRequeued: () => void;
}) {
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
  const open = useOpenFile(refresh); // a failed open usually means the file has gone: re-check
  const title = item.title ?? item.url;
  const onOpen = item.exists ? () => open.mutate(item.id) : undefined;

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
    <li className={`flex items-center gap-3 py-2 ${selected ? 'bg-blue-50/60' : ''}`}>
      <input
        type="checkbox"
        checked={selected}
        onChange={(e) => onSelect(e.target.checked)}
        aria-label={`Select ${title}`}
        className="h-4 w-4 shrink-0"
      />
      <Thumbnail src={item.thumbnail} title={title} onOpen={onOpen} />
      <div className="min-w-0 flex-1">
        <Title text={title} onOpen={onOpen} />
        <p className="truncate text-sm text-slate-600" title={meta}>
          {meta}
          <span
            className={`ml-2 rounded-full px-1.5 py-px text-[11px] font-semibold ${
              item.exists ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'
            }`}
          >
            {item.exists ? 'On disk' : 'Missing'}
          </span>
        </p>
        <p
          className={`truncate text-xs ${item.exists ? 'text-slate-500' : 'text-amber-700'}`}
          title={item.file_path ?? ''}
        >
          {item.exists
            ? baseName(item.file_path)
            : `File missing — was ${baseName(item.file_path)}`}
        </p>
        {open.error && (
          <p role="alert" className="text-sm text-red-700">
            {open.error.message}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {onOpen && <IconButton icon={Play} label="Open" tone="primary" onClick={onOpen} />}
        {item.exists && (
          <IconButton icon={FolderOpen} label="Show file" onClick={() => show.mutate(item.id)} />
        )}
        <IconButton
          icon={RotateCw}
          label="Download again"
          onClick={() => again.mutate(item.id)}
          disabled={again.isPending}
        />
        <IconButton
          icon={Trash2}
          label="Remove"
          tone="danger"
          onClick={() => {
            if (window.confirm('Remove this from the history? The file itself is not touched.'))
              forget.mutate(item.id);
          }}
        />
      </div>
    </li>
  );
}

function MoveDialog({
  count,
  groups,
  busy,
  error,
  onMove,
  onClose,
}: {
  count: number;
  groups: string[];
  busy: boolean;
  error: string | null;
  onMove: (group: string) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState('');
  return (
    <Modal
      title={`Move ${count} ${count === 1 ? 'download' : 'downloads'} into a folder`}
      onClose={onClose}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onMove(name.trim());
        }}
        className="space-y-4"
      >
        <div className="space-y-2">
          <label htmlFor="group" className="block text-sm font-medium text-slate-700">
            Folder name
          </label>
          <input
            id="group"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Road trip"
            className={inputClass}
            autoFocus
          />
          {groups.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {groups.map((g) => (
                <button
                  type="button"
                  key={g}
                  onClick={() => setName(g)}
                  className="rounded-full border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50"
                >
                  {g}
                </button>
              ))}
            </div>
          )}
          <p className="text-xs text-slate-500">
            The files move into a folder with that name inside your downloads folder, and “Download
            again” will put them there too. Leave the name blank to move them back to the main
            folder. Files that have gone missing are skipped.
          </p>
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300"
          >
            {busy ? 'Moving…' : 'Move'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export default function LibraryView({ onRequeued }: { onRequeued: () => void }) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(PAGE);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [moving, setMoving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const library = useQuery({
    queryKey: ['library', query, limit],
    queryFn: () => getLibrary(query, 0, limit),
    placeholderData: (previous) => previous,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['library'] });

  const items = library.data?.items ?? [];
  const chosen = items.filter((i) => selected.has(i.id)); // only rows still listed count
  const allChosen = items.length > 0 && chosen.length === items.length;

  const remove = useMutation({
    mutationFn: removeDownloads,
    onSuccess: (data) => {
      setNotice(`Removed ${data.removed} from the history. The files themselves are untouched.`);
      setSelected(new Set());
      void refresh();
    },
  });
  const move = useMutation({
    mutationFn: ({ ids, group }: { ids: string[]; group: string }) => moveDownloads(ids, group),
    onSuccess: (data) => {
      setNotice(describeMove(data));
      setSelected(new Set());
      setMoving(false);
      void refresh();
    },
  });

  const toggle = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
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
      {items.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={allChosen}
              ref={(el) => {
                if (el) el.indeterminate = chosen.length > 0 && !allChosen;
              }}
              onChange={(e) =>
                setSelected(e.target.checked ? new Set(items.map((i) => i.id)) : new Set())
              }
              aria-label="Select all"
              className="h-4 w-4"
            />
            {chosen.length ? `${chosen.length} selected` : 'Select all'}
          </label>
          {chosen.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <ActionButton
                icon={FolderInput}
                label="Move to folder…"
                tone="primary"
                onClick={() => setMoving(true)}
              />
              <ActionButton
                icon={Trash2}
                label="Remove selected"
                tone="danger"
                disabled={remove.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      `Remove ${chosen.length} from the history? The files themselves are not touched.`
                    )
                  )
                    remove.mutate(chosen.map((i) => i.id));
                }}
              />
              <ActionButton icon={X} label="Clear" onClick={() => setSelected(new Set())} />
            </div>
          )}
        </div>
      )}
      {notice && (
        <p className="flex items-start justify-between gap-2 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-900">
          <span>{notice}</span>
          <button
            type="button"
            onClick={() => setNotice(null)}
            aria-label="Dismiss"
            className="shrink-0 font-semibold"
          >
            ×
          </button>
        </p>
      )}
      {remove.error && (
        <p role="alert" className="rounded-md bg-red-100 p-3 text-red-800">
          {remove.error.message}
        </p>
      )}
      {library.isPending ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : library.error ? (
        <p role="alert" className="rounded-md bg-red-100 p-3 text-red-800">
          {library.error.message}
        </p>
      ) : items.length === 0 ? (
        <p className="text-center text-slate-500">
          {query ? 'Nothing matches that.' : 'Nothing downloaded yet.'}
        </p>
      ) : (
        <>
          <ul className="divide-y divide-slate-100">
            {items.map((item) => (
              <LibraryRow
                key={item.id}
                item={item}
                selected={selected.has(item.id)}
                onSelect={(on) => toggle(item.id, on)}
                onRequeued={onRequeued}
              />
            ))}
          </ul>
          {items.length < (library.data?.total ?? 0) && (
            <button
              type="button"
              onClick={() => setLimit((n) => n + PAGE)}
              className="w-full rounded-md border border-slate-300 py-2 text-sm font-medium hover:bg-slate-50"
            >
              Show more ({(library.data?.total ?? 0) - items.length} left)
            </button>
          )}
        </>
      )}
      {moving && (
        <MoveDialog
          count={chosen.length}
          groups={library.data?.groups ?? []}
          busy={move.isPending}
          error={move.error?.message ?? null}
          onMove={(group) => move.mutate({ ids: chosen.map((i) => i.id), group })}
          onClose={() => setMoving(false)}
        />
      )}
    </section>
  );
}
