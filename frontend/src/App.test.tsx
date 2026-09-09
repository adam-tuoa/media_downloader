import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const json = (data: unknown) =>
  new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

const health = (desktop: boolean, extra: object = {}) => ({
  status: 'ok',
  ytdlp: '2026.08.19',
  version: '0.4.0',
  desktop,
  ytdlp_update: { state: 'idle', message: '' },
  app_update: null,
  quit_requested: false,
  cookies_warning: null,
  ...extra,
});

const settings = {
  output_dir: '/tmp/x',
  concurrency: 2,
  cookies_browser: null,
  audio_language: 'en',
  default_kind: 'video',
  default_video: 'best',
  default_audio: 'mp3-320',
};

function stubApi(healthBody: object, settingsBody: object = settings) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const path = String(url);
      if (path.includes('/api/health')) return json(healthBody);
      if (path.includes('/api/settings')) return json(settingsBody);
      return json([]);
    })
  );
}

function renderApp() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>
  );
}

describe('App', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('renders the form and an empty board', async () => {
    stubApi(health(false));
    renderApp();
    expect(screen.getByRole('heading', { name: 'Media Downloader' })).toBeInTheDocument();
    expect(screen.getByLabelText(/Paste links/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download' })).toBeDisabled();
    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Quit' })).not.toBeInTheDocument();
    // The subtitle checkbox names the Settings language.
    expect(await screen.findByLabelText(/Include English subtitles/)).toBeInTheDocument();
  });

  it('starts the form with the saved defaults', async () => {
    stubApi(health(false), { ...settings, default_kind: 'audio', default_audio: 'm4a' });
    renderApp();
    expect(await screen.findByLabelText('Audio format')).toHaveValue('m4a');
    expect(screen.queryByLabelText('Quality')).not.toBeInTheDocument();
  });

  it('opens Settings and Help as dialogs', async () => {
    stubApi(health(false));
    renderApp();
    fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
    expect(screen.getByRole('dialog', { name: 'Settings' })).toBeInTheDocument();
    expect(await screen.findByLabelText('Language')).toHaveValue('en');
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Help' }));
    expect(screen.getByRole('dialog', { name: 'Help' })).toBeInTheDocument();
    expect(screen.getByText(/Full Disk Access/)).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('warns when the browser cookies could not be read', async () => {
    stubApi(
      health(false, {
        cookies_warning:
          "Couldn't read Safari's cookies (x), so downloads are running without them.",
      })
    );
    renderApp();
    expect(await screen.findByText(/Couldn't read Safari's cookies/)).toBeInTheDocument();
  });

  it('shows Quit and the update banner in desktop mode', async () => {
    stubApi(health(true, { app_update: { latest: '9.9.9', url: 'https://x/rel' } }));
    renderApp();
    expect(await screen.findByRole('button', { name: 'Quit' })).toBeInTheDocument();
    expect(screen.getByText(/9\.9\.9 is available/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download it' })).toHaveAttribute(
      'href',
      'https://x/rel'
    );
  });
});
