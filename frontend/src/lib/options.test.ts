import { describe, expect, it } from 'vitest';
import { describeJob } from './items';
import { AUDIO_CHOICES, audioChoice, languageName, videoHeight } from './options';

describe('options', () => {
  it('maps audio choices to API fields', () => {
    expect(audioChoice('mp3-192')).toMatchObject({ format: 'mp3', bitrate: 192 });
    expect(audioChoice('m4a')).toMatchObject({ format: 'm4a' });
    expect(audioChoice('best').bitrate).toBeUndefined();
    expect(audioChoice('wav')).toMatchObject({ format: 'wav' });
    expect(audioChoice('aiff').bitrate).toBeUndefined();
    expect(audioChoice('nonsense').value).toBe(AUDIO_CHOICES[0].value);
  });
  it('names languages, with null for the original', () => {
    expect(languageName('en')).toBe('English');
    expect(languageName('pt-BR')).toBe('pt-BR');
    expect(languageName('')).toBeNull();
    expect(languageName(undefined)).toBeNull();
  });
  it('maps video quality values to heights', () => {
    expect(videoHeight('best')).toBeNull();
    expect(videoHeight('2160')).toBe(2160);
    expect(videoHeight('720')).toBe(720);
  });
  it('describes jobs in plain words', () => {
    const base = { id: 'j', created_at: 0, archived: false, items: [] };
    expect(describeJob({ ...base, kind: 'audio', options: { audio_format: 'best' } })).toBe(
      'Audio · best original'
    );
    expect(describeJob({ ...base, kind: 'audio', options: { audio_format: 'm4a' } })).toBe(
      'Audio · M4A (original quality)'
    );
    expect(
      describeJob({ ...base, kind: 'audio', options: { audio_format: 'mp3', audio_bitrate: 192 } })
    ).toBe('Audio · MP3 192 kbps');
    expect(describeJob({ ...base, kind: 'audio', options: { audio_format: 'aiff' } })).toBe(
      'Audio · AIFF (uncompressed)'
    );
    expect(
      describeJob({ ...base, kind: 'video', options: { height: 1080, subtitles: true } })
    ).toBe('Video · up to 1080p · subtitles');
    expect(describeJob({ ...base, kind: 'video', options: { height: null } })).toBe(
      'Video · best available'
    );
  });
});
