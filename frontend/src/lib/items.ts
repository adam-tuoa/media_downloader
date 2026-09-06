import type { Item, Job } from '../api';
import { baseName, formatDuration, formatSpeed, percent } from './format';

export function describeItem(item: Item): string {
  switch (item.status) {
    case 'queued':
      return 'Waiting for its turn';
    case 'running': {
      const pct = percent(item.downloaded, item.total);
      const bits = [item.stage ?? 'Working'];
      if (item.stage?.startsWith('Downloading') && pct != null) {
        bits.push(`${pct}%`);
        const speed = formatSpeed(item.speed);
        if (speed) bits.push(speed);
        if (item.eta != null && item.eta > 0) bits.push(`${formatDuration(item.eta)} left`);
      }
      return bits.join(' · ');
    }
    case 'done':
      return baseName(item.file_path) || 'Saved';
    case 'error':
      return item.error ?? 'Something went wrong';
    case 'cancelled':
      return 'Cancelled';
  }
}

/** 0-100 for the progress bar; post-processing stages count as full. */
export function barWidth(item: Item): number {
  if (item.status === 'done') return 100;
  if (item.status !== 'running') return 0;
  if (item.stage && !item.stage.startsWith('Downloading') && !item.stage.startsWith('Starting'))
    return 100;
  return percent(item.downloaded, item.total) ?? 0;
}

export function describeJob(job: Job): string {
  if (job.kind === 'audio') {
    const format = job.options.audio_format ?? 'mp3';
    if (format === 'm4a') return 'Audio · M4A (original quality)';
    if (format === 'best') return 'Audio · best original';
    return `Audio · MP3 ${job.options.audio_bitrate ?? 320} kbps`;
  }
  const quality = job.options.height ? `up to ${job.options.height}p` : 'best available';
  return `Video · ${quality}${job.options.subtitles ? ' · subtitles' : ''}`;
}
