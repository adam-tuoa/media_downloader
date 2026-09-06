import { useMutation, useQuery } from '@tanstack/react-query';
import { getHealth, quitApp } from '../api';

/** Version, update banner, downloader-update notice and (desktop only) Quit. */
export default function StatusBar() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: (query) =>
      query.state.data?.ytdlp_update?.state === 'running' ? 2000 : 60_000,
  });
  const quit = useMutation({ mutationFn: quitApp });
  const h = health.data;

  if (quit.isSuccess || h?.quit_requested) {
    return (
      <div className="rounded-xl bg-white p-8 text-center shadow-md">
        <h2 className="text-xl font-semibold">Media Downloader has quit</h2>
        <p className="mt-2 text-slate-600">
          You can close this tab. Open the app again from its icon.
        </p>
      </div>
    );
  }

  return (
    <>
      {h?.app_update && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-blue-50 px-4 py-3 text-sm text-blue-900">
          <span>
            Media Downloader {h.app_update.latest} is available (you have {h.version}).
          </span>
          <a
            href={h.app_update.url}
            target="_blank"
            rel="noreferrer"
            className="font-semibold underline"
          >
            Download it
          </a>
        </div>
      )}
      {h?.ytdlp_update?.state === 'running' && (
        <p className="rounded-md bg-slate-100 px-4 py-2 text-sm text-slate-600">
          {h.ytdlp_update.message} Downloads will start once that’s done.
        </p>
      )}
      {h?.status === 'degraded' && (
        <p role="alert" className="rounded-md bg-red-100 px-4 py-2 text-sm text-red-800">
          The downloader engine (yt-dlp) isn’t working. Try Settings → Update now, or reinstall.
        </p>
      )}
    </>
  );
}

export function QuitButton() {
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth });
  const quit = useMutation({ mutationFn: quitApp });
  if (!health.data?.desktop) return null;
  return (
    <button
      type="button"
      onClick={() => {
        if (window.confirm('Quit Media Downloader? Downloads in progress will stop.'))
          quit.mutate();
      }}
      className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50"
    >
      Quit
    </button>
  );
}
