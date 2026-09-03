import { BENCHMARKS } from "../lib/data";

const W = 640;
const H = 240;
const PAD_L = 34;
const PAD_B = 24;
const PAD_T = 14;
const GROUP_GAP = 30;
const BAR_GAP = 7;
const RADIUS = 4;

const chartW = W - PAD_L - 12;
const chartH = H - PAD_T - PAD_B;
const groupW = (chartW - GROUP_GAP * (BENCHMARKS.length - 1)) / BENCHMARKS.length;
const barW = (groupW - BAR_GAP) / 2;

function y(pct: number) {
  return PAD_T + chartH - (pct / 100) * chartH;
}

/* Rounded-top bar as a path, so a near-zero value doesn't render an
   impossible rounded rect taller than its own height. */
function barPath(x: number, top: number, w: number, h: number) {
  const r = Math.min(RADIUS, h, w / 2);
  if (h <= 0) return "";
  return `M${x},${top + h} L${x},${top + r} Q${x},${top} ${x + r},${top} L${x + w - r},${top} Q${x + w},${top} ${x + w},${top + r} L${x + w},${top + h} Z`;
}

export function BenchmarkChart() {
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="TRACE fraud-reduction percentage versus behavioral-only scoring and EigenTrust, across four scenarios: sybil cluster 53 and 74 percent, collusion ring 5 and 32 percent, game-theoretic 14 and 69 percent, strategic default 0 and 0 percent (a tie)."
      className="w-full overflow-visible"
    >
      {[0, 25, 50, 75, 100].map((tick) => (
        <g key={tick}>
          <line x1={PAD_L} x2={W - 12} y1={y(tick)} y2={y(tick)} stroke="var(--rule)" strokeWidth={1} />
          <text
            x={PAD_L - 8}
            y={y(tick) + 3}
            textAnchor="end"
            fontSize="9.5"
            fill="var(--ink-faint)"
            fontFamily="var(--font-jetbrains-mono)"
          >
            {tick}
          </text>
        </g>
      ))}

      {BENCHMARKS.map((b, i) => {
        const gx = PAD_L + i * (groupW + GROUP_GAP);
        const behavioralH = chartH - (y(b.behavioral) - PAD_T);
        const eigentrustH = chartH - (y(b.eigentrust) - PAD_T);
        const color = b.tie ? "var(--sienna)" : "var(--bush-bright)";
        return (
          <g key={b.scenario}>
            <path d={barPath(gx, y(b.behavioral), barW, behavioralH)} fill={color} opacity={0.5} />
            <path d={barPath(gx + barW + BAR_GAP, y(b.eigentrust), barW, eigentrustH)} fill={color} />
            <text
              x={gx + groupW / 2}
              y={H - 5}
              textAnchor="middle"
              fontSize="10"
              fill="var(--ink-dim)"
              fontFamily="var(--font-work-sans)"
              fontWeight={500}
            >
              {b.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
