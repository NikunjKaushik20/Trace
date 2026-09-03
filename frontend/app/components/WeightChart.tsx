"use client";

import { motion } from "motion/react";
import { SIGNAL_COMPONENTS } from "../lib/data";
import { useRevealOnce } from "../lib/useReveal";

const MAX_WEIGHT = Math.max(...SIGNAL_COMPONENTS.map((s) => s.weight));

export function WeightChart() {
  const { ref, shown, instant } = useRevealOnce<HTMLDivElement>();

  return (
    <div
      ref={ref}
      role="img"
      aria-label="Score formula weights: LCB 0.40 positive, default risk 0.30 negative, sybil risk 0.35 negative, clique penalty 0.25 negative, price anomaly 0.15 negative, graph trust 0.10 positive, capability match 0.10 positive."
      className="glass overflow-hidden rounded-[24px]"
    >
      {SIGNAL_COMPONENTS.map((s, i) => (
        <div
          key={s.key}
          className={`flex flex-col gap-2 px-6 py-4 sm:flex-row sm:items-center sm:gap-5 ${
            i !== SIGNAL_COMPONENTS.length - 1 ? "border-b border-rule/70" : ""
          }`}
        >
          <div className="w-full shrink-0 text-[13.5px] sm:w-52">
            <span
              className={`font-display mr-1.5 text-base italic ${
                s.direction === "positive" ? "text-bush-bright" : "text-sienna-deep"
              }`}
            >
              {s.symbol}
            </span>
            <span className="text-ink">{s.label}</span>
          </div>
          <div className="relative h-3.5 flex-1 overflow-hidden rounded-full bg-paper-deep">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: shown ? `${(s.weight / MAX_WEIGHT) * 100}%` : 0 }}
              transition={{ duration: instant ? 0 : 0.8, ease: [0.16, 1, 0.3, 1], delay: instant ? 0 : i * 0.05 }}
              className={`h-full rounded-full ${s.direction === "positive" ? "bg-bush-bright" : "bg-sienna"}`}
            />
          </div>
          <div className="tnum w-12 shrink-0 text-right text-[12.5px] text-ink-dim">
            {s.weight.toFixed(2)}
          </div>
        </div>
      ))}
    </div>
  );
}
