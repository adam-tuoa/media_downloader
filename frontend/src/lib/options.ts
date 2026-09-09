import type { AudioBitrate, AudioFormat } from '../api';

export interface AudioChoice {
  value: string;
  label: string;
  format: AudioFormat;
  bitrate?: AudioBitrate;
  note: string;
}

export const AUDIO_CHOICES: AudioChoice[] = [
  {
    value: 'mp3-320',
    label: 'MP3 · 320 kbps — plays everywhere',
    format: 'mp3',
    bitrate: 320,
    note: 'The safe choice. An MP3 can’t sound better than the original (about 130 kbps on YouTube), so 320 is about compatibility, not extra quality.',
  },
  {
    value: 'mp3-192',
    label: 'MP3 · 192 kbps — smaller files',
    format: 'mp3',
    bitrate: 192,
    note: 'Same as above with files about 40% smaller; hard to tell apart from 320.',
  },
  {
    value: 'mp3-128',
    label: 'MP3 · 128 kbps — smallest',
    format: 'mp3',
    bitrate: 128,
    note: 'Fine for speech and podcasts.',
  },
  {
    value: 'm4a',
    label: 'M4A (AAC) — original quality, Apple-friendly',
    format: 'm4a',
    note: 'YouTube’s own AAC stream copied as-is, no re-encoding. Plays in Apple Music, iPhones, cars and most players.',
  },
  {
    value: 'best',
    label: 'Best original — highest quality, untouched',
    format: 'best',
    note: 'Exactly what the site has: Opus from YouTube, MP3 from Bandcamp. Opus needs VLC or a modern player.',
  },
  {
    value: 'wav',
    label: 'WAV — uncompressed, for editing',
    format: 'wav',
    note: 'Huge files (about 10× an MP3) and no better than the original — only worth it if you’ll edit the audio. WAV can’t hold cover art.',
  },
  {
    value: 'aiff',
    label: 'AIFF — uncompressed, Apple flavour',
    format: 'aiff',
    note: 'The same as WAV in Apple’s container, for Logic, GarageBand and the like. Huge files, no cover art.',
  },
];

/** The one language setting: used for YouTube’s dubbed audio tracks and for subtitles. */
export const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: '', label: 'Original (as uploaded)' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
  { value: 'it', label: 'Italian' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'hi', label: 'Hindi' },
  { value: 'ja', label: 'Japanese' },
  { value: 'ko', label: 'Korean' },
  { value: 'zh', label: 'Chinese' },
  { value: 'ar', label: 'Arabic' },
  { value: 'id', label: 'Indonesian' },
];

/** Plain name for a language code; null means "the original, whatever it is". */
export function languageName(code: string | null | undefined): string | null {
  if (!code) return null;
  return LANGUAGES.find((l) => l.value === code)?.label ?? code;
}

export const DEFAULT_AUDIO_CHOICE = 'mp3-320';

export function audioChoice(value: string): AudioChoice {
  return AUDIO_CHOICES.find((c) => c.value === value) ?? AUDIO_CHOICES[0];
}

export const VIDEO_QUALITIES: { value: string; label: string; height: number | null }[] = [
  { value: 'best', label: 'Best available', height: null },
  { value: '2160', label: '2160p (4K)', height: 2160 },
  { value: '1440', label: '1440p', height: 1440 },
  { value: '1080', label: '1080p', height: 1080 },
  { value: '720', label: '720p', height: 720 },
  { value: '480', label: '480p', height: 480 },
  { value: '360', label: '360p (small)', height: 360 },
];

export function videoHeight(value: string): number | null {
  return VIDEO_QUALITIES.find((q) => q.value === value)?.height ?? null;
}

export const DEFAULT_VIDEO_QUALITY = 'best';

/** A saved video-quality value, or the default when it isn't one we know. */
export function videoQuality(value: string | null | undefined): string {
  return VIDEO_QUALITIES.some((q) => q.value === value) ? String(value) : DEFAULT_VIDEO_QUALITY;
}
