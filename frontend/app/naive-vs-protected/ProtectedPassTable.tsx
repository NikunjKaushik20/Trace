"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import type { Attempt } from "../lib/data";

const DECISION_COLOR: Record<string, string> = {
  ROUTE_WITH_CAUTION: "text-bush-bright",
  DENY: "text-sienna-deep",
  QUARANTINE: "text-sienna-deep",
};

export function ProtectedPassTable({ rows }: { rows: Attempt[] }) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="glass overflow-hidden rounded-[24px]">
      <div className="grid grid-cols-[1.4fr_1fr_1.2fr_1.4fr_0.7fr] gap-2 border-b border-rule/70 bg-paper-deep/50 px-5 py-3 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
        <span>Agent</span>
        <span>Class</span>
        <span>Status</span>
        <span>Decision</span>
        <span className="text-right">Score</span>
      </div>
      {rows.map((a) => {
        const isOpen = openId === a.agentId;
        return (
          <div key={a.agentId} className="border-b border-rule/70 last:border-none">
            <button
              onClick={() => setOpenId(isOpen ? null : a.agentId)}
              aria-expanded={isOpen}
              className="grid w-full grid-cols-[1.4fr_1fr_1.2fr_1.4fr_0.7fr] items-center gap-2 px-5 py-3.5 text-left text-[13.5px] transition-colors hover:bg-paper-deep/40"
            >
              <span className="tnum flex items-center gap-2 text-ink">
                <span className={`inline-block transition-transform ${isOpen ? "rotate-90" : ""}`}>›</span>
                {a.agentId}
              </span>
              <span className="text-ink-dim">{a.agentClass}</span>
              <span className={a.status === "blocked" ? "text-sienna-deep" : "text-bush-bright"}>
                {a.status === "blocked" ? "Blocked" : "Order created"}
              </span>
              <span className={DECISION_COLOR[a.decision] ?? "text-ink-dim"}>{a.decision}</span>
              <span className="tnum text-right font-medium text-ink">{a.score.toFixed(2)}</span>
            </button>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                  className="overflow-hidden"
                >
                  <div className="border-t border-rule/70 bg-paper-deep/40 px-5 py-3.5 pl-11">
                    {a.flags.length > 0 && (
                      <p className="text-[12px] text-sienna-deep">{a.flags.join(" · ")}</p>
                    )}
                    <p className="prose mt-1.5 text-[13px] leading-relaxed text-ink-dim">{a.explanation}</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
