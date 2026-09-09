import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../api';

const RELEASES = 'https://github.com/adam-tuoa/media_downloader/releases/latest';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="font-semibold">{title}</h3>
      <div className="space-y-2 text-sm text-slate-700">{children}</div>
    </section>
  );
}

/** The short guide for people who won’t read the README. Plain words, in the order things happen. */
export default function HelpPanel() {
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth });
  return (
    <div className="space-y-6">
      <Section title="Getting started">
        <p>
          Paste one or more links — YouTube, Vimeo or Bandcamp — one per line. Single videos go
          straight to the queue. Playlists and albums show their entries first so you can untick any
          you don’t want.
        </p>
        <p>Choose Video or Audio, then press Download. Everything else is optional.</p>
      </Section>

      <Section title="Video or Audio">
        <p>
          <strong>Video:</strong> pick a size. If the video isn’t available at that size you get the
          next one down. Tick the subtitles box to include them in the language chosen in Settings,
          when the video has real (not auto-generated) subtitles.
        </p>
        <p>
          <strong>Audio:</strong> MP3 320 plays on anything. M4A keeps YouTube’s own audio with no
          re-encoding. “Best original” keeps exactly what the site has (Opus files need VLC or a
          modern player). WAV and AIFF are uncompressed — huge, and no better than the original —
          for editing only. Turning a long recording into an MP3 takes a while; that’s normal.
        </p>
        <p>Cover art and title/artist tags are added automatically where the format allows.</p>
      </Section>

      <Section title="Where files go">
        <p>
          Into the folder set under Settings → “Save downloads to”. Playlists and albums get a
          folder of their own with numbered tracks. “Show file” opens the folder with the file
          selected.
        </p>
        <p>
          The <strong>Library</strong> lists everything ever downloaded, says whether each file is
          still where it was put, and can download again anything that has gone missing. Tick a few
          and choose “Add to playlist” to move them into a folder of their own; the playlist names
          across the top show one at a time.
        </p>
      </Section>

      <Section title="Signing in (cookies)">
        <p>
          Some videos need an account: everything on Vimeo, and private, members-only or age-checked
          videos elsewhere. Sign in on your normal browser, then in Settings set “Use cookies from”
          to that browser and try again.
        </p>
        <p>
          Firefox works best. Safari on a Mac needs Media Downloader switched on under System
          Settings → Privacy &amp; Security → Full Disk Access first. Chrome on Windows often
          refuses to share its cookies — use Firefox or Edge instead.
        </p>
      </Section>

      <Section title="When something breaks">
        <p>
          If YouTube suddenly stops working, open Settings and press “Update now” — the download
          engine changes often, and the app also updates it every time it starts. A failed item can
          be retried from the board.
        </p>
        <p>A banner appears at the top when a new version of the app is ready to download.</p>
      </Section>

      <Section title="Quitting">
        <p>
          The Quit button stops the app; just closing the browser tab doesn’t. Open it again from
          its icon.
        </p>
      </Section>

      <p className="border-t border-slate-100 pt-4 text-xs text-slate-500">
        Media Downloader {health.data?.version ?? ''} ·{' '}
        <a href={RELEASES} target="_blank" rel="noreferrer" className="underline">
          downloads page
        </a>
      </p>
    </div>
  );
}
