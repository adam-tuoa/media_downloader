import { useState } from 'react';
import JobsBoard from './components/JobsBoard';
import NewJobForm from './components/NewJobForm';
import SettingsPanel from './components/SettingsPanel';

export default function App() {
  const [showSettings, setShowSettings] = useState(false);

  return (
    <main className="mx-auto w-full max-w-3xl space-y-5 p-4 sm:p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Media Downloader</h1>
        <button
          type="button"
          onClick={() => setShowSettings((s) => !s)}
          aria-expanded={showSettings}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50"
        >
          {showSettings ? 'Close settings' : 'Settings'}
        </button>
      </header>

      <NewJobForm />
      {showSettings && <SettingsPanel />}
      <JobsBoard />
    </main>
  );
}
