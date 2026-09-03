"use client";

import { useEffect, useRef, useState } from "react";
import { useInView } from "motion/react";

/* Shared scroll-reveal logic for Reveal.tsx and TrustRoots.tsx.

   A fast or programmatic scroll (a long trackpad flick, a jump to an
   anchor, an automated test) can carry an element from below the
   viewport to above it between two observed frames, so the normal
   IntersectionObserver trigger never fires and the content would stay
   invisible forever. The scroll fallback here catches exactly that: an
   element already scrolled past without ever having triggered reveals
   instantly rather than staying hidden. */
type InViewMargin = NonNullable<Parameters<typeof useInView>[1]>["margin"];

export function useRevealOnce<T extends Element>(margin: InViewMargin = "0px 0px -60px 0px") {
  const ref = useRef<T>(null);
  const inView = useInView(ref, { once: true, margin });
  const [passed, setPassed] = useState(false);

  useEffect(() => {
    if (inView) return;
    function check() {
      const el = ref.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (rect.bottom < -40) setPassed(true);
    }
    check();
    window.addEventListener("scroll", check, { passive: true });
    return () => window.removeEventListener("scroll", check);
  }, [inView]);

  return { ref, shown: inView || passed, instant: passed && !inView };
}
