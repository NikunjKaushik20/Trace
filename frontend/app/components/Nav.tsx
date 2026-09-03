"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence, useScroll, useMotionValueEvent } from "motion/react";
import { NAV } from "../lib/nav";
import { CommandPalette } from "./CommandPalette";

export function Nav() {
  const pathname = usePathname();
  const [hovered, setHovered] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const { scrollY } = useScroll();

  useMotionValueEvent(scrollY, "change", (v) => setScrolled(v > 12));

  // Close the drawer on navigation -- adjusted during render (React's
  // documented pattern for resetting state when a prop changes) rather
  // than in an effect.
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    if (drawerOpen) setDrawerOpen(false);
  }

  return (
    <>
      <header
        className={`sticky top-0 z-40 transition-[box-shadow,border-color] duration-300 ${
          scrolled ? "border-b border-rule" : "border-b border-transparent"
        }`}
      >
        <div className="glass-sm">
          <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-5 py-3 sm:px-8">
            <Link
              href="/"
              className="font-display flex items-baseline gap-2 text-[22px] font-semibold italic tracking-tight text-ink"
            >
              TRACE
              <span className="h-1.5 w-1.5 rounded-full bg-sienna align-middle" aria-hidden />
            </Link>

            <nav
              aria-label="Primary"
              className="relative hidden items-center gap-0.5 lg:flex"
              onMouseLeave={() => setHovered(null)}
            >
              {NAV.map((item) => {
                const isActive = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onMouseEnter={() => setHovered(item.href)}
                    aria-current={isActive ? "page" : undefined}
                    className={`relative z-10 rounded-full px-3.5 py-2 text-[13.5px] font-medium transition-colors ${
                      isActive ? "text-sienna-deep" : "text-ink-dim hover:text-ink"
                    }`}
                  >
                    {hovered === item.href && (
                      <motion.span
                        layoutId="nav-pill"
                        className="absolute inset-0 -z-10 rounded-full bg-sienna-bg/80 ring-1 ring-sienna/15"
                        transition={{ type: "spring", stiffness: 420, damping: 34 }}
                      />
                    )}
                    {isActive && hovered !== item.href && (
                      <span className="absolute inset-x-3.5 bottom-1 h-[2px] rounded-full bg-sienna" aria-hidden />
                    )}
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            <div className="flex items-center gap-3">
              <div className="hidden sm:block">
                <CommandPalette />
              </div>
              <Link
                href="/try-it"
                className="hidden items-center gap-1.5 rounded-full bg-bush px-4 py-2 text-[12.5px] font-semibold text-paper transition-transform hover:-translate-y-0.5 hover:shadow-[0_10px_24px_-10px_rgba(31,61,44,0.55)] sm:inline-flex"
              >
                Try it live
              </Link>
              <button
                onClick={() => setDrawerOpen(true)}
                aria-label="Open navigation"
                aria-expanded={drawerOpen}
                className="flex h-9 w-9 flex-col items-center justify-center gap-[4px] rounded-full border border-rule bg-panel/70 lg:hidden"
              >
                <span className="h-px w-4 bg-ink" />
                <span className="h-px w-4 bg-ink" />
                <span className="h-px w-3 bg-ink" />
              </button>
            </div>
          </div>
        </div>
      </header>

      <AnimatePresence>
        {drawerOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-40 bg-[#241a10]/45 backdrop-blur-[2px] lg:hidden"
              onClick={() => setDrawerOpen(false)}
            />
            <motion.aside
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
              className="glass-sm fixed inset-y-0 right-0 z-50 flex w-[86vw] max-w-sm flex-col rounded-l-[28px] lg:hidden"
              role="dialog"
              aria-label="Navigation"
            >
              <div className="flex items-center justify-between border-b border-rule px-6 py-5">
                <span className="font-display text-lg font-semibold italic">TRACE</span>
                <button
                  onClick={() => setDrawerOpen(false)}
                  aria-label="Close navigation"
                  className="flex h-8 w-8 items-center justify-center rounded-full border border-rule text-[15px]"
                >
                  ×
                </button>
              </div>
              <nav aria-label="Primary" className="flex flex-1 flex-col gap-1 px-4 py-6">
                {NAV.map((item, i) => {
                  const isActive = pathname === item.href;
                  return (
                    <motion.div
                      key={item.href}
                      initial={{ opacity: 0, x: 16 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.05 + i * 0.035, duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                    >
                      <Link
                        href={item.href}
                        aria-current={isActive ? "page" : undefined}
                        className={`font-display block rounded-2xl px-4 py-3 text-xl font-medium transition-colors ${
                          isActive ? "bg-sienna-bg text-sienna-deep" : "text-ink hover:bg-paper-deep"
                        }`}
                      >
                        {item.full}
                      </Link>
                    </motion.div>
                  );
                })}
              </nav>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
