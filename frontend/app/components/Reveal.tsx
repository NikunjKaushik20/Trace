"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { useRevealOnce } from "../lib/useReveal";

/* One motion grammar for every scroll-triggered reveal on the site:
   fade + rise, exponential ease-out, once per element. */
export function Reveal({
  children,
  delay = 0,
  className,
  y = 26,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
  y?: number;
}) {
  const { ref, shown, instant } = useRevealOnce<HTMLDivElement>();

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y }}
      animate={shown ? { opacity: 1, y: 0 } : { opacity: 0, y }}
      transition={{ duration: instant ? 0 : 0.7, ease: [0.16, 1, 0.3, 1], delay: instant ? 0 : delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
