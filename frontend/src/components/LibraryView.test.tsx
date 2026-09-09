import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
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

describe('LibraryView', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('lists downloads with file status and re-queues on request', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push(`${init?.method ?? 'GET'} ${url}`);
        if (String(url).includes('/redownload')) return json({ id: 'j2', items: [] });
        return json({
          items: [
            item({}),
            item({
              id: 'i2',
              title: 'Gone',
              exists: false,
              file_path: '/x/Gone.mp3',
              collection: null,
            }),
          ],
          total: 2,
          offset: 0,
          groups: ['Mixtape'],
        });
      })
    );
    const onRequeued = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LibraryView onRequeued={onRequeued} />
      </QueryClientProvider>
    );
    expect(await screen.findByText('A Song')).toBeInTheDocument();
    expect(screen.getByText('2 downloads')).toBeInTheDocument();
    expect(screen.getByText(/Mixtape · #3/)).toBeInTheDocument();
    expect(screen.getByText('On disk')).toBeInTheDocument();
    expect(screen.getByText('Missing')).toBeInTheDocument();
    expect(screen.getByText(/File missing — was Gone.mp3/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Show file' })).toHaveLength(1); // only for files on disk

    fireEvent.click(screen.getAllByRole('button', { name: 'Download again' })[1]);
    await vi.waitFor(() => expect(onRequeued).toHaveBeenCalled());
    expect(calls).toContain('POST /api/library/i2/redownload');

    // A file on disk opens from its title; a missing one is plain text.
    fireEvent.click(screen.getByRole('button', { name: 'A Song' }));
    await vi.waitFor(() => expect(calls).toContain('POST /api/items/i1/open'));
    expect(screen.queryByRole('button', { name: 'Gone' })).not.toBeInTheDocument();
  });

  it('moves and removes selected downloads', async () => {
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
        return json({
          items: [item({}), item({ id: 'i2', title: 'Gone', exists: false, collection: null })],
          total: 2,
          offset: 0,
          groups: ['Mixtape'],
        });
      })
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LibraryView onRequeued={() => {}} />
      </QueryClientProvider>
    );
    await screen.findByText('A Song');
    fireEvent.click(screen.getByLabelText('Select all'));
    expect(screen.getByText('2 selected')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Move to folder…' }));
    fireEvent.click(screen.getByRole('button', { name: 'Mixtape' })); // an existing group fills the name
    expect(screen.getByLabelText('Folder name')).toHaveValue('Mixtape');
    fireEvent.change(screen.getByLabelText('Folder name'), { target: { value: 'Road trip' } });
    fireEvent.click(screen.getByRole('button', { name: 'Move' }));
    expect(
      await screen.findByText(/Moved 1 into “Road trip”\. Skipped 1: Gone \(file missing\)\./)
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
