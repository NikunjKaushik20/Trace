"use client";

import { motion } from "motion/react";
import { useRevealOnce } from "../lib/useReveal";

/* The signature interaction: an authored root-network diagram of the
   real mechanism behind trust_net in api/scorer.py — Personalized
   PageRank flowing outward from an honest seed. Connected nodes draw
   in as growing roots once the diagram enters view.

   Geometry note: on the landing hero, this sits behind a glass "live
   decision" card whose position (and size, relative to this diagram's
   viewBox) shifts noticeably with viewport width, since the card has a
   fixed max-width while this SVG scales with a flexible grid column.
   Below 1440px the card occupies too much of the viewBox for any fixed
   coordinate set to clear it, so page.tsx only shows this diagram from
   1440px up. At that width and above, page.tsx also renders a blurred
   paper-colored glow behind the card itself -- that's what actually
   keeps nearby strokes reading as "behind the glass" instead of
   "touching the edge," rather than chasing exact pixel gaps here. */

const GROWN_PATHS = [
  { d: "M45,300 C55,270 62,240 68,210", delay: 0 },
  { d: "M68,210 C72,175 75,140 78,105", delay: 0.28 },
  { d: "M78,105 C78,80 76,55 72,32", delay: 0.56 },
  { d: "M78,105 C55,100 32,105 20,128", delay: 0.5 },
  { d: "M45,300 C58,360 66,410 75,442", delay: 0.12 },
  { d: "M75,442 C160,458 260,455 360,447", delay: 0.4 },
  { d: "M360,447 C420,443 470,440 510,436", delay: 0.65 },
];

const NODES = [
  { cx: 45, cy: 300, r: 8, fill: "var(--bush)", ring: true },
  { cx: 68, cy: 210, r: 5.5, fill: "var(--bush-bright)" },
  { cx: 78, cy: 105, r: 6, fill: "var(--bush-bright)" },
  { cx: 72, cy: 32, r: 5, fill: "var(--oak)" },
  { cx: 20, cy: 128, r: 4.5, fill: "var(--oak)" },
  { cx: 75, cy: 442, r: 5.5, fill: "var(--bush-bright)" },
  { cx: 360, cy: 447, r: 5, fill: "var(--oak)" },
  { cx: 510, cy: 436, r: 5.5, fill: "var(--oak)" },
];

export function TrustRoots({ className }: { className?: string }) {
  const { ref, shown, instant } = useRevealOnce<SVGSVGElement>();

  return (
    <svg
      ref={ref}
      viewBox="0 0 640 480"
      className={className}
      role="img"
      aria-label="Trust propagating as a root network from an honest seed agent outward through the trust graph."
    >
      {/* faint decorative undergrowth — non-animated texture, low opacity,
          kept in the same left/below safe zone as the grown paths above */}
      <g opacity={0.16} stroke="var(--oak)" strokeWidth={1} fill="none">
        <path d="M20,455 C50,448 75,452 95,460" />
        <path d="M400,455 C430,448 460,452 485,460" />
        <path d="M580,55 C595,40 612,48 625,32" />
        <path d="M100,30 C130,20 160,25 185,18" />
      </g>

      {/* grown paths — the real signal */}
      {GROWN_PATHS.map((p, i) => (
        <motion.path
          key={i}
          d={p.d}
          fill="none"
          stroke="var(--bush-bright)"
          strokeWidth={2}
          strokeLinecap="round"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={shown ? { pathLength: 1, opacity: 0.9 } : { pathLength: 0, opacity: 0 }}
          transition={{ duration: instant ? 0 : 1, ease: [0.16, 1, 0.3, 1], delay: instant ? 0 : p.delay }}
        />
      ))}

      {NODES.map((n, i) => (
        <g key={i}>
          {n.ring && (
            <motion.circle
              cx={n.cx}
              cy={n.cy}
              r={n.r}
              fill="none"
              stroke="var(--bush)"
              strokeWidth={1.5}
              initial={{ opacity: 0.5, scale: 1 }}
              animate={{ opacity: [0.45, 0, 0.45], scale: [1, 2.6, 1] }}
              transition={{ duration: 3.2, repeat: Infinity, ease: "easeOut" }}
              style={{ transformOrigin: `${n.cx}px ${n.cy}px` }}
            />
          )}
          <motion.circle
            cx={n.cx}
            cy={n.cy}
            r={n.r}
            fill={n.fill}
            initial={{ opacity: 0, scale: 0.4 }}
            animate={shown ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.4 }}
            transition={{
              duration: instant ? 0 : 0.5,
              delay: instant ? 0 : (GROWN_PATHS[i]?.delay ?? 0) + 0.15,
            }}
            style={{ transformOrigin: `${n.cx}px ${n.cy}px` }}
          />
        </g>
      ))}

      <text
        x={45}
        y={324}
        textAnchor="middle"
        fontSize="11"
        fontFamily="var(--font-work-sans)"
        fill="var(--bush)"
        opacity={0.8}
      >
        honest seed
      </text>
    </svg>
  );
}
