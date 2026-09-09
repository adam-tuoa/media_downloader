import type { LucideIcon } from 'lucide-react';

const TONES = {
  default: 'border-slate-200 text-slate-700 hover:bg-slate-100',
  primary: 'border-blue-200 text-blue-800 hover:bg-blue-50',
  danger: 'border-red-200 text-red-700 hover:bg-red-50',
};

/** A small button with an icon *and* a word - icons alone are a gamble for a non-technical user. */
export default function ActionButton({
  icon: Icon,
  label,
  onClick,
  disabled = false,
  tone = 'default',
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: keyof typeof TONES;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-md border bg-white px-2.5 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${TONES[tone]}`}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {label}
    </button>
  );
}
