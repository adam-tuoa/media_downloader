import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const json = (data: unknown) =>
  new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

describe('App', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('renders the form and an empty board', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json([]))
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>
    );
    expect(screen.getByRole('heading', { name: 'Media Downloader' })).toBeInTheDocument();
    expect(screen.getByLabelText('Paste one or more links, one per line')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download' })).toBeDisabled();
    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument();
  });
});
