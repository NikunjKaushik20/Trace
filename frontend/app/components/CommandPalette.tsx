"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "motion/react";
import { NAV } from "../lib/nav";

const HINTS: Record<string, string> = {
  "/": "the pitch",
  "/try-it": "score a real purchase",
  "/naive-vs-protected": "the before/after proof",
  "/marketplace": "the agent population",
  "/pricing": "trust-gated tiers",
  "/outcomes": "benchmarks + scale",
  "/audit": "what's real vs. in progress",
};

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const results = NAV.filter(
    (p) =>
      p.full.toLowerCase().includes(query.toLowerCase()) ||
      HINTS[p.href].toLowerCase().includes(query.toLowerCase())
  );

  // Reset the active row whenever the query changes -- adjusted during
  // render (React's documented pattern for this) rather than in an
  // effect, so opening/typing never round-trips through a second render.
  const [prevQuery, setPrevQuery] = useState(query);
  if (query !== prevQuery) {
    setPrevQuery(query);
    setActive(0);
  }

  function openPalette() {
    setQuery("");
    setActive(0);
    setOpen(true);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) setOpen(false);
        else openPalette();
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function go(href: string) {
    setOpen(false);
    router.push(href);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && results[active]) {
      e.preventDefault();
      go(results[active].href);
    }
  }

  return (
    <>
      <button
        onClick={openPalette}
        className="flex items-center gap-2 rounded-full border border-rule bg-panel/60 px-3 py-1.5 text-[12px] text-ink-dim transition-colors hover:border-sienna/40 hover:text-ink"
        aria-label="Open command palette"
      >
        Jump to
        <kbd className="tnum rounded-md border border-rule bg-paper px-1.5 py-0.5 text-[10px]">⌘K</kbd>
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="fixed inset-0 z-50 bg-[#241a10]/50 backdrop-blur-[3px]"
              onClick={() => setOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, y: -12, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.98 }}
              transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              className="glass-sm fixed left-1/2 top-24 z-50 w-[90vw] max-w-lg -translate-x-1/2 overflow-hidden rounded-[24px]"
              role="dialog"
              aria-label="Command palette"
            >
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Jump to a page…"
                className="w-full border-b border-rule bg-transparent px-5 py-4 text-[15px] text-ink outline-none placeholder:text-ink-faint"
              />
              <div className="max-h-80 overflow-y-auto p-1.5">
                {results.length === 0 && (
                  <p className="px-4 py-6 text-center text-[12px] text-ink-dim">No pages match.</p>
                )}
                {results.map((p, i) => (
                  <button
                    key={p.href}
                    onClick={() => go(p.href)}
                    onMouseEnter={() => setActive(i)}
                    className={`flex w-full items-center justify-between rounded-2xl px-4 py-2.5 text-left text-[13.5px] transition-colors ${
                      i === active ? "bg-sienna-bg text-sienna-deep" : "text-ink-dim"
                    }`}
                  >
                    <span className="font-medium">{p.full}</span>
                    <span className="text-[11px] text-ink-faint">{HINTS[p.href]}</span>
                  </button>
                ))}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
