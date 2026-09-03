"use client";

import { useEffect, useState } from "react";
import { animate } from "motion/react";
import { useRevealOnce } from "../lib/useReveal";

export function CountUp({
  value,
  format,
  duration = 1.1,
  className,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
  className?: string;
}) {
  const { ref, shown, instant } = useRevealOnce<HTMLSpanElement>();
  const fmt = format ?? ((n: number) => Math.round(n).toString());
  const [animatedDisplay, setAnimatedDisplay] = useState(fmt(0));

  useEffect(() => {
    if (!shown || instant) return;
    const controls = animate(0, value, {
      duration,
      ease: "easeOut",
      onUpdate: (v) => setAnimatedDisplay(fmt(v)),
    });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown, instant, value, duration]);

  // The instant (scrolled-past-without-triggering) case is a pure
  // derived value -- computed during render, never written to state.
  const display = shown && instant ? fmt(value) : animatedDisplay;

  return (
    <span ref={ref} className={className}>
      {display}
    </span>
  );
}
