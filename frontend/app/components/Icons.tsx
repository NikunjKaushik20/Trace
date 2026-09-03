/* Authored line icons, one consistent stroke (1.75) and cap (round)
   throughout — drawn for this system, not a generic icon-library grab
   and not unicode/emoji standing in for one. */

type IconProps = { className?: string };

const base = {
  viewBox: "0 0 40 40",
  fill: "none",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function ConfidenceIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M8 30V12" />
      <path d="M8 12l-3.5 4.5" />
      <path d="M8 12l3.5 4.5" />
      <path d="M8 30h24" />
      <path d="M16 30v-9.5" strokeDasharray="2 3.2" opacity={0.55} />
      <circle cx="16" cy="20.5" r="2" />
      <path d="M16 20.5c4-6.5 8-8.5 16-9" />
    </svg>
  );
}

export function ChangePointIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M5 26h9" />
      <path d="M14 26L21 9" />
      <path d="M21 9l3 5.5" />
      <path d="M21 9l-5 2.6" opacity={0.55} />
      <path d="M24 14.5c3 6 6 9 11 9.5" />
      <circle cx="21" cy="9" r="2.1" />
    </svg>
  );
}

export function GraphIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M9 27c4-9 10-14 17-15.5" />
      <path d="M9 27c6 1.5 12 0.5 17-4" />
      <path d="M9 27l7 5.5" />
      <circle cx="9" cy="27" r="2.6" />
      <circle cx="26" cy="11.5" r="2" />
      <circle cx="26" cy="23" r="2" />
      <circle cx="16" cy="32.5" r="1.8" />
    </svg>
  );
}

export function SybilIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden>
      <path d="M14 12l10 2.3" strokeDasharray="2 3" />
      <path d="M14 12L11 23.5" strokeDasharray="2 3" />
      <path d="M24 14.3l-6 12.7" strokeDasharray="2 3" />
      <circle cx="14" cy="12" r="2.4" />
      <circle cx="24" cy="14.3" r="2.4" />
      <circle cx="11" cy="23.5" r="2.4" />
      <path d="M32 20a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z" opacity={0.5} />
      <path d="M25 27l4 4" opacity={0.5} />
    </svg>
  );
}
