import { describe, expect, it } from 'vitest';
import { formatBytes, formatDuration } from './format';

describe('formatDuration', () => {
  it('formats minutes and seconds', () => {
    expect(formatDuration(0)).toBe('0:00');
    expect(formatDuration(5)).toBe('0:05');
    expect(formatDuration(125)).toBe('2:05');
  });
  it('adds hours when needed', () => {
    expect(formatDuration(3725)).toBe('1:02:05');
  });
  it('is empty for unknown values', () => {
    expect(formatDuration(null)).toBe('');
    expect(formatDuration(undefined)).toBe('');
    expect(formatDuration(-1)).toBe('');
  });
});

describe('formatBytes', () => {
  it('picks a sensible unit', () => {
    expect(formatBytes(999)).toBe('999 B');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(250 * 1024 ** 2)).toBe('250 MB');
    expect(formatBytes(3 * 1024 ** 3)).toBe('3.0 GB');
  });
  it('is empty for unknown values', () => {
    expect(formatBytes(null)).toBe('');
    expect(formatBytes(0)).toBe('');
  });
});
