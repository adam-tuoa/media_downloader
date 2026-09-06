import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
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
  ...extra,
});

function stubApi(healthBody: object) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => json(String(url).includes('/api/health') ? healthBody : []))
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
