import { useMutation, useQueryClient } from '@tanstack/react-query';
import { cancelItem, retryItem, reveal, type Item } from '../api';
import { barWidth, describeItem } from '../lib/items';

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
  const show = useMutation({ mutationFn: reveal });

  const style = STATUS_STYLE[item.status];
  const title = item.title ?? item.url;
  const indeterminate =
    item.status === 'running' && barWidth(item) === 0 && item.stage !== 'Downloading';

  return (
    <li className="flex items-start gap-3 py-3">
      <div className="h-12 w-20 shrink-0 overflow-hidden rounded bg-slate-200">
        {item.thumbnail && (
          <img src={item.thumbnail} alt="" className="h-full w-full object-cover" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate font-medium" title={title}>
          {title}
        </p>
        <p
          className={`truncate text-sm ${item.status === 'error' ? 'text-red-700' : 'text-slate-600'}`}
          title={describeItem(item)}
        >
          {describeItem(item)}
        </p>
        <div className="mt-2 h-2 w-full overflow-hidden rounded bg-slate-100">
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

      <div className="flex shrink-0 flex-col items-end gap-2">
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${style.chip}`}>
          {style.label}
        </span>
        {(item.status === 'queued' || item.status === 'running') && (
          <button
            type="button"
            onClick={() => cancel.mutate(item.id)}
            className="text-sm text-slate-600 underline hover:text-slate-900"
          >
            Cancel
          </button>
        )}
        {(item.status === 'error' || item.status === 'cancelled') && (
          <button
            type="button"
            onClick={() => retry.mutate(item.id)}
            className="text-sm text-blue-700 underline hover:text-blue-900"
          >
            Retry
          </button>
        )}
        {item.status === 'done' && (
          <button
            type="button"
            onClick={() => show.mutate(item.id)}
            className="text-sm text-blue-700 underline hover:text-blue-900"
          >
            Show file
          </button>
        )}
      </div>
    </li>
  );
}
