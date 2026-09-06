import type { InspectResult, LinkInfo, NewLink } from '../api';

/** One link per line; trimmed, blanks dropped, duplicates removed, order kept. */
export function parseLinks(text: string): string[] {
  return Array.from(
    new Set(
      text
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean)
    )
  );
}

/** Playlists need the user to choose entries; problems should be seen before anything starts. */
export function needsReview(result: InspectResult): boolean {
  return result.errors.length > 0 || result.links.some((l) => l.kind === 'playlist');
}

export function allEntryUrls(result: InspectResult): Set<string> {
  return new Set(result.links.flatMap((l) => (l.entries ?? []).map((e) => e.url)));
}

/** The links to queue: every video, plus the selected entries of every playlist, in order. */
export function collectLinks(result: InspectResult, selected: Set<string>): NewLink[] {
  const out: NewLink[] = [];
  const seen = new Set<string>();
  const push = (link: NewLink) => {
    if (!seen.has(link.url)) {
      seen.add(link.url);
      out.push(link);
    }
  };
  for (const link of result.links) {
    if (link.kind === 'video') {
      push({ url: link.url, title: link.title ?? null, thumbnail: link.thumbnail ?? null });
    } else {
      const entries = link.entries ?? [];
      entries.forEach((e, i) => {
        if (selected.has(e.url)) {
          push({
            url: e.url,
            title: e.title,
            thumbnail: e.thumbnail,
            collection: link.title ?? null,
            collection_index: i + 1,
          });
        }
      });
    }
  }
  return out;
}

export function playlistLabel(link: LinkInfo): string {
  const shown = link.entries?.length ?? 0;
  const count = link.count ?? shown;
  return link.truncated ? `first ${shown} of ${count} entries` : `${count} entries`;
}
