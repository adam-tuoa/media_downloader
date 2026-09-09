import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LibraryItem } from '../api';
import LibraryView from './LibraryView';

const json = (data: unknown) =>
  new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

const item = (over: Partial<LibraryItem>): LibraryItem => ({
  id: 'i1',
  job_id: 'j1',
  position: 0,
  url: 'https://www.youtube.com/watch?v=abc',
  status: 'done',
  title: 'A Song',
  uploader: null,
  duration: 200,
  thumbnail: null,
  stage: 'Done',
  downloaded: 1,
  total: 1,
  speed: null,
  eta: null,
  file_path: '/x/Music/A Song.m4a',
  error: null,
  created_at: 1,
  started_at: 1,
  finished_at: 1_700_000_000,
  collection: 'Mixtape',
  collection_index: 3,
  kind: 'audio',
  options: { audio_format: 'm4a' },
  exists: true,
  ...over,
});

const page = {
  items: [
    item({}),
    item({ id: 'i2', title: 'Gone', exists: false, file_path: '/x/Gone.mp3', collection: null }),
  ],
  total: 2,
  offset: 0,
  groups: ['Mixtape'],
};

function renderLibrary(onRequeued = () => {}) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <LibraryView onRequeued={onRequeued} />
    </QueryClientProvider>
  );
}

describe('LibraryView', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('lists downloads with file status, re-queues, opens files and browses playlists', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? 'GET'} ${url}`);
        if (String(url).includes('/redownload')) return json({ id: 'j2', items: [] });
        if (String(url).includes('/api/reveal')) return json({ ok: true, path: '/x' });
        return json(page);
      })
    );
    const onRequeued = vi.fn();
    renderLibrary(onRequeued);
    expect(await screen.findByText('A Song')).toBeInTheDocument();
    expect(screen.getByText('2 downloads')).toBeInTheDocument();
    expect(screen.getByText(/#3/)).toBeInTheDocument();
    expect(screen.getByText('On disk')).toBeInTheDocument();
    expect(screen.getByText('Missing')).toBeInTheDocument();
    expect(screen.getByText(/File missing — was Gone.mp3/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Show file' })).toHaveLength(1); // on disk only

    fireEvent.click(screen.getAllByRole('button', { name: 'Download again' })[1]);
    await vi.waitFor(() => expect(onRequeued).toHaveBeenCalled());
    expect(calls).toContain('POST /api/library/i2/redownload');

    // A file on disk opens from its title; a missing one is plain text.
    fireEvent.click(screen.getByRole('button', { name: 'A Song' }));
    await vi.waitFor(() => expect(calls).toContain('POST /api/items/i1/open'));
    expect(screen.queryByRole('button', { name: 'Gone' })).not.toBeInTheDocument();

    // The playlist name in a row narrows the list to that playlist; its folder can be opened.
    fireEvent.click(screen.getByTitle('Show this playlist'));
    await vi.waitFor(() =>
      expect(calls.some((c) => c.includes('/api/library?') && c.includes('group=Mixtape'))).toBe(
        true
      )
    );
    expect(await screen.findByText(/in “Mixtape”/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open folder' }));
    await vi.waitFor(() => expect(calls).toContain('POST /api/reveal'));
    fireEvent.click(screen.getByRole('button', { name: 'All' }));
    await vi.waitFor(() => expect(screen.queryByText(/in “Mixtape”/)).not.toBeInTheDocument());
  });

  it('adds selected downloads to a playlist and removes them', async () => {
    const calls: { method: string; url: string; body?: unknown }[] = [];
    vi.stubGlobal('confirm', () => true);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        const entry = {
          method: init?.method ?? 'GET',
          url: String(url),
          body: init?.body ? JSON.parse(String(init.body)) : undefined,
        };
        calls.push(entry);
        if (entry.url.includes('/api/library/move'))
          return json({
            moved: 1,
            skipped: [{ id: 'i2', title: 'Gone', reason: 'file missing' }],
            group: 'Road trip',
          });
        if (entry.url.includes('/api/library/remove')) return json({ ok: true, removed: 2 });
        return json(page);
      })
    );
    renderLibrary();
    await screen.findByText('A Song');
    fireEvent.click(screen.getByLabelText('Select all'));
    expect(screen.getByText('2 selected')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Add to playlist…' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mixtape' })); // existing playlist
    expect(screen.getByLabelText('Playlist name')).toHaveValue('Mixtape');
    fireEvent.change(screen.getByLabelText('Playlist name'), { target: { value: 'Road trip' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));
    expect(
      await screen.findByText(/Added 1 to “Road trip”\. Skipped 1: Gone \(file missing\)\./)
    ).toBeInTheDocument();
    expect(calls.find((c) => c.url.includes('/api/library/move'))?.body).toEqual({
      item_ids: ['i1', 'i2'],
      group: 'Road trip',
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Select all'));
    fireEvent.click(screen.getByRole('button', { name: 'Remove selected' }));
    await screen.findByText(/Removed 2 from the history/);
    expect(calls.find((c) => c.url.includes('/api/library/remove'))?.body).toEqual({
      item_ids: ['i1', 'i2'],
    });
  });
});
