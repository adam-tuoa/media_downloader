import { useCallback, useState } from 'react';
import HelpPanel from './components/HelpPanel';
import JobsBoard from './components/JobsBoard';
import LibraryView from './components/LibraryView';
import Modal from './components/Modal';
import NewJobForm from './components/NewJobForm';
import SettingsPanel from './components/SettingsPanel';
import StatusBar, { QuitButton } from './components/StatusBar';
import { segmentClass } from './lib/ui';

type View = 'downloads' | 'library';
type Panel = 'settings' | 'help' | null;

const headerButton =
  'rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50';

export default function App() {
  const [view, setView] = useState<View>('downloads');
  const [panel, setPanel] = useState<Panel>(null);
  const closePanel = useCallback(() => setPanel(null), []);

  return (
    <main className="mx-auto w-full max-w-3xl space-y-5 p-4 sm:p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Media Downloader</h1>
        <div className="flex gap-2">
          <button type="button" onClick={() => setPanel('settings')} className={headerButton}>
            Settings
          </button>
          <button type="button" onClick={() => setPanel('help')} className={headerButton}>
            Help
          </button>
          <QuitButton />
        </div>
      </header>

      <StatusBar />
      {panel === 'settings' && (
        <Modal title="Settings" onClose={closePanel} wide>
          <SettingsPanel />
        </Modal>
      )}
      {panel === 'help' && (
        <Modal title="Help" onClose={closePanel}>
          <HelpPanel />
        </Modal>
      )}

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
