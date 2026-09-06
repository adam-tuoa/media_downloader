import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { Item } from '../api';
import ItemRow from './ItemRow';
import { barWidth, describeItem } from '../lib/items';
import { parseLinks } from '../lib/links';

const base: Item = {
  id: 'i1',
  job_id: 'j1',
  position: 0,
  url: 'https://youtu.be/abc',
  status: 'queued',
  title: null,
  uploader: null,
  duration: null,
  thumbnail: null,
  stage: null,
  downloaded: null,
  total: null,
  speed: null,
  eta: null,
  file_path: null,
  error: null,
  created_at: 0,
  started_at: null,
  finished_at: null,
};

describe('describe / barWidth', () => {
  it('reports download progress with speed and time left', () => {
    const item: Item = {
      ...base,
      status: 'running',
      stage: 'Downloading',
      downloaded: 50 * 1024 ** 2,
      total: 200 * 1024 ** 2,
      speed: 5 * 1024 ** 2,
      eta: 30,
    };
    expect(describeItem(item)).toBe('Downloading · 25% · 5.0 MB/s · 0:30 left');
    expect(barWidth(item)).toBe(25);
    expect(describeItem({ ...item, stage: 'Downloading audio' })).toBe(
      'Downloading audio · 25% · 5.0 MB/s · 0:30 left'
    );
    expect(barWidth({ ...item, stage: 'Downloading video' })).toBe(25);
  });
  it('fills the bar during post-processing and when done', () => {
    expect(barWidth({ ...base, status: 'running', stage: 'Converting audio' })).toBe(100);
    expect(barWidth({ ...base, status: 'done' })).toBe(100);
    expect(barWidth({ ...base, status: 'error' })).toBe(0);
  });
  it('shows the file name when done and the error when failed', () => {
    expect(describeItem({ ...base, status: 'done', file_path: '/x/y/Song [abc].mp3' })).toBe(
      'Song [abc].mp3'
    );
    expect(describeItem({ ...base, status: 'error', error: 'Video unavailable' })).toBe(
      'Video unavailable'
    );
  });
});

describe('ItemRow', () => {
  it('shows the URL until a title is known, and the right action', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ItemRow item={base} />
      </QueryClientProvider>
    );
    expect(screen.getByText('https://youtu.be/abc')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });
  it('offers Retry after a failure', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <ItemRow item={{ ...base, status: 'error', error: 'boom', title: 'A video' }} />
      </QueryClientProvider>
    );
    expect(screen.getByText('A video')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});

describe('parseLinks', () => {
  it('splits lines, trims, drops blanks and duplicates', () => {
    expect(parseLinks(' https://a \n\nhttps://b\r\nhttps://a\n')).toEqual([
      'https://a',
      'https://b',
    ]);
  });
});
