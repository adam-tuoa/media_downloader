import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { InspectResult } from '../api';
import { collectLinks, needsReview, allEntryUrls, playlistLabel } from '../lib/links';
import ReviewPanel from './ReviewPanel';

const result: InspectResult = {
  links: [
    {
      input: 'a',
      url: 'https://www.youtube.com/watch?v=aaaaaaaaaaa',
      site: 'youtube',
      kind: 'video',
    },
    {
      input: 'p',
      url: 'https://www.youtube.com/playlist?list=PL1',
      site: 'youtube',
      kind: 'playlist',
      title: 'Mix',
      count: 3,
      truncated: false,
      entries: [
        { url: 'https://www.youtube.com/watch?v=e1', title: 'One', duration: 61, thumbnail: null },
        { url: 'https://www.youtube.com/watch?v=e2', title: 'Two', duration: 62, thumbnail: null },
        {
          url: 'https://www.youtube.com/watch?v=e3',
          title: 'Three',
          duration: 63,
          thumbnail: null,
        },
      ],
    },
  ],
  errors: [{ input: 'https://soundcloud.com/x', message: "soundcloud.com isn't supported" }],
};

describe('review helpers', () => {
  it('decides when a review is needed', () => {
    expect(needsReview(result)).toBe(true);
    expect(needsReview({ links: [result.links[0]], errors: [] })).toBe(false);
    expect(needsReview({ links: [], errors: result.errors })).toBe(true);
  });
  it('collects videos plus selected entries without duplicates', () => {
    const all = allEntryUrls(result);
    expect(collectLinks(result, all).map((l) => l.url)).toEqual([
      'https://www.youtube.com/watch?v=aaaaaaaaaaa',
      'https://www.youtube.com/watch?v=e1',
      'https://www.youtube.com/watch?v=e2',
      'https://www.youtube.com/watch?v=e3',
    ]);
    expect(collectLinks(result, new Set(['https://www.youtube.com/watch?v=e2']))).toHaveLength(2);
    expect(collectLinks(result, new Set())[0].title).toBeNull();
    const second = collectLinks(result, all)[2];
    expect(second.collection).toBe('Mix');
    expect(second.collection_index).toBe(2);
    expect(collectLinks(result, all)[0].collection).toBeUndefined();
  });
  it('labels truncated playlists', () => {
    expect(playlistLabel(result.links[1])).toBe('3 entries');
    expect(playlistLabel({ ...result.links[1], count: 500, truncated: true })).toBe(
      'first 3 of 500 entries'
    );
  });
});

describe('ReviewPanel', () => {
  it('lists problems and entries, and confirms the selection', () => {
    const onConfirm = vi.fn();
    render(<ReviewPanel result={result} busy={false} onConfirm={onConfirm} onBack={() => {}} />);
    expect(screen.getByText(/isn't supported/)).toBeInTheDocument();
    expect(screen.getByText('Mix')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Download 4 items' })).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Two/));
    fireEvent.click(screen.getByRole('button', { name: 'Download 3 items' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm.mock.calls[0][0].map((l: { url: string }) => l.url)).toEqual([
      'https://www.youtube.com/watch?v=aaaaaaaaaaa',
      'https://www.youtube.com/watch?v=e1',
      'https://www.youtube.com/watch?v=e3',
    ]);

    fireEvent.click(screen.getByRole('button', { name: 'None' }));
    expect(screen.getByRole('button', { name: 'Download 1 item' })).toBeInTheDocument();
  });
});
