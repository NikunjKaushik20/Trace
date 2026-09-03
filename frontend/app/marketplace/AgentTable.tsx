"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import type { Attempt } from "../lib/data";

const CLASS_LABEL: Record<string, string> = {
  honest: "Honest",
  defector: "Strategic defector",
  sybil: "Sybil ring",
};

export function AgentTable({ rows }: { rows: Attempt[] }) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="glass overflow-hidden rounded-[24px]">
      <div className="grid grid-cols-[1.6fr_1.4fr_0.6fr_1.8fr] gap-2 border-b border-rule/70 bg-paper-deep/50 px-5 py-3 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
        <span>Agent</span>
        <span>Class</span>
        <span className="text-right">Score</span>
        <span>Flags</span>
      </div>
      {rows.map((a) => {
        const isOpen = openId === a.agentId;
        return (
          <div key={a.agentId} className="border-b border-rule/70 last:border-none">
            <button
              onClick={() => setOpenId(isOpen ? null : a.agentId)}
              aria-expanded={isOpen}
              className="grid w-full grid-cols-[1.6fr_1.4fr_0.6fr_1.8fr] items-center gap-2 px-5 py-3.5 text-left text-[13.5px] transition-colors hover:bg-paper-deep/40"
            >
              <span className="tnum flex items-center gap-2 text-ink">
                <span className={`inline-block transition-transform ${isOpen ? "rotate-90" : ""}`}>›</span>
                {a.agentId}
              </span>
              <span className="text-ink-dim">{CLASS_LABEL[a.agentClass]}</span>
              <span className="tnum text-right font-medium text-ink">{a.score.toFixed(2)}</span>
              <span className={a.flags.length ? "text-[12px] text-sienna-deep" : "text-ink-faint"}>
                {a.flags.length ? a.flags.join(" · ") : "—"}
              </span>
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
                  <p className="prose border-t border-rule/70 bg-paper-deep/40 px-5 py-3.5 pl-11 text-[13px] leading-relaxed text-ink-dim">
                    {a.explanation}
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
