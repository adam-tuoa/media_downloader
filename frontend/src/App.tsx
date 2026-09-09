import { useState } from 'react';
import JobsBoard from './components/JobsBoard';
import LibraryView from './components/LibraryView';
import NewJobForm from './components/NewJobForm';
import SettingsPanel from './components/SettingsPanel';
import StatusBar, { QuitButton } from './components/StatusBar';
import { segmentClass } from './lib/ui';

type View = 'downloads' | 'library';

export default function App() {
  const [view, setView] = useState<View>('downloads');
  const [showSettings, setShowSettings] = useState(false);

  return (
    <main className="mx-auto w-full max-w-3xl space-y-5 p-4 sm:p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Media Downloader</h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setShowSettings((s) => !s)}
            aria-expanded={showSettings}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50"
          >
            {showSettings ? 'Close settings' : 'Settings'}
          </button>
          <QuitButton />
        </div>
      </header>

      <StatusBar />
      {showSettings && <SettingsPanel />}

      <nav className="flex gap-2 rounded-lg bg-slate-200 p-1" aria-label="View">
        <button
          type="button"
          className={segmentClass(view === 'downloads')}
          onClick={() => setView('downloads')}
        >
          Downloads
        </button>
        <button
          type="button"
          className={segmentClass(view === 'library')}
          onClick={() => setView('library')}
        >
          Library
        </button>
      </nav>

      {view === 'downloads' ? (
        <>
          <NewJobForm />
          <JobsBoard />
        </>
      ) : (
        <LibraryView onRequeued={() => setView('downloads')} />
      )}
    </main>
  );
}
