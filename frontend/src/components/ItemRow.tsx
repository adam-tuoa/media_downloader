import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FolderOpen, Play, RotateCw, X } from 'lucide-react';
import { cancelItem, retryItem, reveal, type Item } from '../api';
import { barWidth, describeItem } from '../lib/items';
import { useOpenFile } from '../lib/openFile';
import { Thumbnail, Title } from './FileLink';
import IconButton from './IconButton';

const STATUS_STYLE: Record<Item['status'], { chip: string; bar: string; label: string }> = {
  queued: { chip: 'bg-slate-200 text-slate-700', bar: 'bg-slate-300', label: 'Waiting' },
  running: { chip: 'bg-blue-100 text-blue-800', bar: 'bg-blue-500', label: 'Working' },
  done: { chip: 'bg-green-100 text-green-800', bar: 'bg-green-500', label: 'Done' },
  error: { chip: 'bg-red-100 text-red-800', bar: 'bg-red-400', label: 'Failed' },
  cancelled: { chip: 'bg-slate-200 text-slate-600', bar: 'bg-slate-300', label: 'Cancelled' },
};

export default function ItemRow({ item }: { item: Item }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['jobs'] });
  const cancel = useMutation({ mutationFn: cancelItem, onSuccess: refresh });
  const retry = useMutation({ mutationFn: retryItem, onSuccess: refresh });
  const show = useMutation({ mutationFn: (id: string) => reveal(id) });
  const open = useOpenFile();

  const style = STATUS_STYLE[item.status];
  const title = item.title ?? item.url;
  const onOpen = item.status === 'done' && item.file_path ? () => open.mutate(item.id) : undefined;
  const indeterminate =
    item.status === 'running' && barWidth(item) === 0 && item.stage !== 'Downloading';
  const active = item.status === 'queued' || item.status === 'running';
  const failed = item.status === 'error' || item.status === 'cancelled';

  return (
    <li className="flex items-center gap-3 py-2">
      <Thumbnail src={item.thumbnail} title={title} onOpen={onOpen} />

      <div className="min-w-0 flex-1">
        <Title text={title} onOpen={onOpen} />
        <p
          className={`truncate text-sm ${item.status === 'error' ? 'text-red-700' : 'text-slate-600'}`}
          title={describeItem(item)}
        >
          {describeItem(item)}
        </p>
        {open.error && (
          <p role="alert" className="text-sm text-red-700">
            {open.error.message}
          </p>
        )}
        <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded bg-slate-100">
          <div
            role="progressbar"
            aria-valuenow={barWidth(item)}
            aria-valuemin={0}
            aria-valuemax={100}
            className={`h-full rounded transition-[width] duration-300 ${style.bar} ${indeterminate ? 'animate-pulse' : ''}`}
            style={{ width: `${indeterminate ? 100 : barWidth(item)}%` }}
          />
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className={`rounded-full px-1.5 py-px text-[11px] font-semibold ${style.chip}`}>
          {style.label}
        </span>
        <div className="flex items-center gap-1">
          {active && <IconButton icon={X} label="Cancel" onClick={() => cancel.mutate(item.id)} />}
          {failed && (
            <IconButton
              icon={RotateCw}
              label="Retry"
              tone="primary"
              onClick={() => retry.mutate(item.id)}
            />
          )}
          {onOpen && <IconButton icon={Play} label="Open" tone="primary" onClick={onOpen} />}
          {item.status === 'done' && (
            <IconButton icon={FolderOpen} label="Show file" onClick={() => show.mutate(item.id)} />
          )}
        </div>
      </div>
    </li>
  );
}
