import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { cancelJob, deleteJob, jobHasActive, listJobs, type Job } from '../api';
import { formatWhen } from '../lib/format';
import { describeJob } from '../lib/items';
import ItemRow from './ItemRow';

function JobCard({ job }: { job: Job }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['jobs'] });
  const cancel = useMutation({ mutationFn: cancelJob, onSuccess: refresh });
  const remove = useMutation({ mutationFn: deleteJob, onSuccess: refresh });
  const active = jobHasActive(job);

  return (
    <section className="rounded-xl bg-white p-4 shadow-md sm:p-5">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-slate-100 pb-2">
        <div className="text-sm text-slate-600">
          <span className="font-medium text-slate-800">{describeJob(job)}</span>
          <span className="mx-2">·</span>
          {formatWhen(job.created_at)}
        </div>
        <div className="flex gap-3 text-sm">
          {active && job.items.length > 1 && (
            <button
              type="button"
              onClick={() => cancel.mutate(job.id)}
              className="text-slate-600 underline hover:text-slate-900"
            >
              Cancel all
            </button>
          )}
          <button
            type="button"
            onClick={() => remove.mutate(job.id)}
            className="text-slate-500 underline hover:text-slate-800"
            title="Removes this from the list; files stay where they are"
          >
            Remove
          </button>
        </div>
      </header>
      <ul className="divide-y divide-slate-100">
        {job.items.map((item) => (
          <ItemRow key={item.id} item={item} />
        ))}
      </ul>
    </section>
  );
}

export default function JobsBoard() {
  const jobs = useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    refetchInterval: (query) => (query.state.data?.some(jobHasActive) ? 1000 : 5000),
  });

  if (jobs.isPending) return <p className="text-center text-slate-500">Loading…</p>;
  if (jobs.error)
    return (
      <p role="alert" className="rounded-md bg-red-100 p-3 text-red-800">
        Can’t reach the downloader: {jobs.error.message}
      </p>
    );
  if (!jobs.data.length)
    return <p className="text-center text-slate-500">Nothing yet — paste a link above to start.</p>;

  return (
    <div className="space-y-4">
      {jobs.data.map((job) => (
        <JobCard key={job.id} job={job} />
      ))}
    </div>
  );
}
