const box = 'h-12 w-20 shrink-0 overflow-hidden rounded bg-slate-200';

/** The thumbnail; a button that opens the file when ``onOpen`` is given. */
export function Thumbnail({
  src,
  title,
  onOpen,
}: {
  src: string | null;
  title: string;
  onOpen?: () => void;
}) {
  const image = src ? <img src={src} alt="" className="h-full w-full object-cover" /> : null;
  if (!onOpen) return <div className={box}>{image}</div>;
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Open ${title}`}
      title="Open in your player"
      className={`${box} cursor-pointer hover:ring-2 hover:ring-blue-300`}
    >
      {image}
    </button>
  );
}

/** The title line; a link-styled button that opens the file when ``onOpen`` is given. */
export function Title({ text, onOpen }: { text: string; onOpen?: () => void }) {
  if (!onOpen) {
    return (
      <p className="truncate font-medium" title={text}>
        {text}
      </p>
    );
  }
  return (
    <button
      type="button"
      onClick={onOpen}
      title="Open in your player"
      className="block max-w-full cursor-pointer truncate text-left font-medium text-blue-800 hover:underline"
    >
      {text}
    </button>
  );
}
