import { describe, expect, it } from 'vitest';
import { filenameFrom } from './api';

describe('filenameFrom', () => {
  it('prefers the RFC 5987 encoded name', () => {
    const header = `attachment; filename="Cafe.mp4"; filename*=utf-8''Caf%C3%A9%20%5Babc%5D.mp4`;
    expect(filenameFrom(header)).toBe('Café [abc].mp4');
  });
  it('falls back to the plain name', () => {
    expect(filenameFrom('attachment; filename="Me at the zoo [jNQXAC9IVRw].mp4"')).toBe(
      'Me at the zoo [jNQXAC9IVRw].mp4'
    );
    expect(filenameFrom('attachment; filename=song.mp3')).toBe('song.mp3');
  });
  it('handles a missing header', () => {
    expect(filenameFrom(null)).toBeNull();
    expect(filenameFrom('inline')).toBeNull();
  });
});
