import { describe, expect, it } from 'vitest';
import { baseName, formatBytes, formatDuration, formatSpeed, percent } from './format';

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

describe('formatBytes / formatSpeed', () => {
  it('picks a sensible unit', () => {
    expect(formatBytes(999)).toBe('999 B');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(250 * 1024 ** 2)).toBe('250 MB');
    expect(formatBytes(3 * 1024 ** 3)).toBe('3.0 GB');
    expect(formatSpeed(3.2 * 1024 ** 2)).toBe('3.2 MB/s');
  });
  it('is empty for unknown values', () => {
    expect(formatBytes(null)).toBe('');
    expect(formatBytes(0)).toBe('');
    expect(formatSpeed(null)).toBe('');
  });
});

describe('percent', () => {
  it('rounds and clamps', () => {
    expect(percent(50, 200)).toBe(25);
    expect(percent(300, 200)).toBe(100);
    expect(percent(1, 3)).toBe(33);
  });
  it('is null without a total', () => {
    expect(percent(10, null)).toBeNull();
    expect(percent(null, 10)).toBeNull();
    expect(percent(10, 0)).toBeNull();
  });
});

describe('baseName', () => {
  it('handles both separators', () => {
    expect(baseName('/Users/adam/Downloads/Song [id].mp3')).toBe('Song [id].mp3');
    expect(baseName('C:\\Users\\Dad\\Downloads\\Song [id].mp3')).toBe('Song [id].mp3');
    expect(baseName(null)).toBe('');
  });
});
