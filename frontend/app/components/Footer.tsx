import Link from "next/link";

const COMPANY_LINKS = [
  { href: "/about", label: "About us" },
  { href: "https://linkedin.com/in/nikunjkaushik2005", label: "LinkedIn", external: true },
  { href: "https://github.com/NikunjKaushik20/TRACE-API", label: "GitHub", external: true },
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/terms", label: "Terms of Service" },
];

export function Footer() {
  return (
    <footer className="relative z-[1] mt-20 border-t border-rule bg-paper-deep">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-x-8 gap-y-4 px-5 py-8 sm:px-8">
        <p className="font-display flex items-baseline gap-2 text-xl font-semibold italic text-ink">
          TRACE
          <span className="h-1.5 w-1.5 rounded-full bg-sienna" aria-hidden />
        </p>

        <ul className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px]">
          {COMPANY_LINKS.map((item) =>
            item.external ? (
              <li key={item.href}>
                <a
                  href={item.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-ink-dim transition-colors hover:text-sienna-deep"
                >
                  {item.label}
                </a>
              </li>
            ) : (
              <li key={item.href}>
                <Link href={item.href} className="text-ink-dim transition-colors hover:text-sienna-deep">
                  {item.label}
                </Link>
              </li>
            )
          )}
        </ul>
      </div>

      <div className="border-t border-rule">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2 px-5 py-5 text-[11.5px] text-ink-faint sm:px-8">
          <span>© {new Date().getFullYear()} TRACE. Bayesian trust scoring for agent-to-agent commerce.</span>
          <span className="tnum">formula ref · api/scorer.py</span>
        </div>
      </div>
    </footer>
  );
}
