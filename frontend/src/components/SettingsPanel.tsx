import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getSettings, reveal, saveSettings, type Settings } from '../api';
import { inputClass } from '../lib/ui';

function SettingsForm({ initial }: { initial: Settings }) {
  const queryClient = useQueryClient();
  const [folder, setFolder] = useState(initial.output_dir);
  const [concurrency, setConcurrency] = useState(initial.concurrency);

  const save = useMutation({
    mutationFn: saveSettings,
    onSuccess: (data) => queryClient.setQueryData(['settings'], data),
  });
  const open = useMutation({ mutationFn: () => reveal() });

  const dirty = folder !== initial.output_dir || concurrency !== initial.concurrency;

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

      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={() => save.mutate({ output_dir: folder, concurrency })}
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

export default function SettingsPanel() {
  const settings = useQuery({ queryKey: ['settings'], queryFn: getSettings });

  return (
    <section className="space-y-4 rounded-xl bg-white p-5 shadow-md sm:p-6">
      <h2 className="text-lg font-semibold">Settings</h2>
      {settings.data ? (
        // Keyed on the saved values so the form resets to them after a save or refetch.
        <SettingsForm
          key={`${settings.data.output_dir}|${settings.data.concurrency}`}
          initial={settings.data}
        />
      ) : settings.error ? (
        <p role="alert" className="text-sm text-red-700">
          {settings.error.message}
        </p>
      ) : (
        <p className="text-sm text-slate-500">Loading…</p>
      )}
    </section>
  );
}
