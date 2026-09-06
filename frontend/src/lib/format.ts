/** 125 -> "2:05", 3725 -> "1:02:05". Empty string for unknown. */
export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null || !Number.isFinite(totalSeconds) || totalSeconds < 0) return '';
  const s = Math.round(totalSeconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

/** 1536 -> "1.5 KB", 262144000 -> "250 MB". Empty string for unknown. */
export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  const text = i > 0 && value < 10 ? value.toFixed(1) : String(Math.round(value));
  return `${text} ${units[i]}`;
}

/** 3355443 -> "3.2 MB/s". Empty string for unknown. */
export function formatSpeed(bytesPerSecond: number | null | undefined): string {
  const text = formatBytes(bytesPerSecond);
  return text ? `${text}/s` : '';
}

/** Whole-number percentage, or null when the total is unknown. */
export function percent(
  done: number | null | undefined,
  total: number | null | undefined
): number | null {
  if (done == null || !total || total <= 0) return null;
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)));
}

/** Last path segment, for either separator. */
export function baseName(path: string | null | undefined): string {
  if (!path) return '';
  const parts = path.split(/[\\/]/);
  return parts[parts.length - 1] ?? '';
}

/** Unix seconds -> "Sat 14:32" style label in the viewer's locale. */
export function formatWhen(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString([], {
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}
