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
