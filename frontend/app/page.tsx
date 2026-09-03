"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { CountUp } from "./components/CountUp";
import { BenchmarkChart } from "./components/BenchmarkChart";
import { TrustRoots } from "./components/TrustRoots";
import { Reveal } from "./components/Reveal";
import { ConfidenceIcon, ChangePointIcon, GraphIcon, SybilIcon } from "./components/Icons";
import { NAIVE_VS_PROTECTED } from "./lib/data";

const SIGNALS = [
  {
    name: "Confidence bound",
    detail: "Thin history reads as thin. It's a Bayesian lower bound, not a raw completion average.",
    Icon: ConfidenceIcon,
  },
  {
    name: "Change-point detect",
    detail: "A sudden default spike after a clean record gets caught by CUSUM, and stays caught.",
    Icon: ChangePointIcon,
  },
  {
    name: "Graph trust",
    detail: "Personalized PageRank from proven-honest seeds. Proximity has to be earned, not claimed.",
    Icon: GraphIcon,
  },
  {
    name: "Sybil defense",
    detail: "A ring vouching for itself without completing real work stands out structurally.",
    Icon: SybilIcon,
  },
];

export default function Home() {
  const { naive, protected: guarded } = NAIVE_VS_PROTECTED;

  return (
    <>
      {/* ---------------------------------------------------------------
          HERO — the mechanism, demonstrated: a real captured decision
          sits in a glass panel over a growing root-network of the trust
          graph. Not a claim about the product; the product, at work.
      --------------------------------------------------------------- */}
      <section className="relative overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
          <div className="blob blob-sienna" />
          <div className="blob blob-bush" />
          <div className="blob blob-oak" />
        </div>

        <div className="mx-auto max-w-[1400px] px-5 pb-20 pt-14 sm:px-8 sm:pb-28 sm:pt-20 lg:grid lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-10 lg:pt-24">
          <motion.div
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.75, ease: [0.16, 1, 0.3, 1] }}
          >
            <h1 className="font-display max-w-xl text-[2.6rem] font-semibold leading-[1.06] tracking-tight text-ink sm:text-[3.4rem] lg:text-[4.1rem]">
              Decide trust <em className="text-bush font-medium not-italic">before</em> the
              money moves.
            </h1>
            <p className="prose mt-6 max-w-md text-[16.5px] leading-relaxed text-ink-dim">
              TRACE scores every autonomous AI purchase in real time, then explains the decision
              in plain language, before a rupee is at risk.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-5">
              <Link
                href="/try-it"
                className="group inline-flex items-center gap-2 rounded-full bg-bush px-7 py-3.5 text-[14.5px] font-semibold text-paper shadow-[0_14px_30px_-12px_rgba(31,61,44,0.55)] transition-all hover:-translate-y-0.5 hover:shadow-[0_20px_38px_-14px_rgba(31,61,44,0.6)]"
              >
                Try it live
                <span className="transition-transform group-hover:translate-x-1">→</span>
              </Link>
              <Link
                href="/naive-vs-protected"
                className="text-[14px] font-medium text-sienna-deep underline decoration-sienna/40 underline-offset-4 transition-colors hover:decoration-sienna"
              >
                See the before and after
              </Link>
            </div>

            <div className="mt-14 flex flex-wrap gap-x-10 gap-y-6">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.13em] text-ink-faint">
                  Fraud prevented
                </p>
                <p className="tnum mt-1.5 text-2xl font-semibold text-ink">
                  ₹600 <span className="text-ink-faint">→</span>{" "}
                  <span className="text-bush-bright">₹0</span>
                </p>
              </div>
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.13em] text-ink-faint">
                  False positives
                </p>
                <p className="tnum mt-1.5 text-2xl font-semibold text-bush-bright">0/20</p>
              </div>
              <div>
                <p className="text-[11px] font-medium uppercase tracking-[0.13em] text-ink-faint">
                  Fraud caught
                </p>
                <p className="tnum mt-1.5 text-2xl font-semibold text-ink">
                  <CountUp value={16} />/16
                </p>
              </div>
            </div>
          </motion.div>

          {/* Live decision readout — real captured example, in glass */}
          <div className="relative mt-16 lg:mt-0">
            {/* Only shown from 1440px: measured directly against the card's
                rendered position (see TrustRoots.tsx's geometry note) --
                below that width the card takes up too much of the
                diagram's own viewBox for any layout to keep them apart,
                so a plain hero here beats a diagram cutting through the
                card's text. */}
            <TrustRoots className="pointer-events-none absolute -right-14 top-[-7rem] hidden w-[122%] max-w-none opacity-95 min-[1440px]:block" />
            <div className="relative mx-auto max-w-md">
              {/* Soft paper-colored glow behind the card: blends any diagram
                  strokes that land just outside the card's edge into the
                  background, instead of relying on pixel-exact coordinate
                  avoidance holding at every viewport width. */}
              <div
                aria-hidden
                className="pointer-events-none absolute -inset-16 hidden rounded-[40px] bg-paper opacity-90 blur-3xl min-[1440px]:block"
              />
              <motion.div
                initial={{ opacity: 0, y: 26, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
                className="glass relative z-10 overflow-hidden rounded-[28px]"
              >
              <div className="flex items-center justify-between border-b border-rule/70 px-6 py-4">
                <span className="tnum text-[13px] text-ink-dim">agent_sybil_0</span>
                <span className="flex items-center gap-1.5 rounded-full bg-sienna-bg px-2.5 py-1 text-[11.5px] font-semibold text-sienna-deep">
                  <span className="h-1.5 w-1.5 rounded-full bg-sienna-deep" />
                  QUARANTINED
                </span>
              </div>
              <div className="grid grid-cols-3 divide-x divide-rule/70 border-b border-rule/70">
                <div className="px-5 py-4">
                  <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Score</p>
                  <p className="tnum mt-1 text-lg font-semibold text-ink">0.00</p>
                </div>
                <div className="px-5 py-4">
                  <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Allow</p>
                  <p className="mt-1 text-lg font-semibold text-sienna-deep">No</p>
                </div>
                <div className="px-5 py-4">
                  <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Latency</p>
                  <p className="tnum mt-1 text-lg font-semibold text-ink">4ms</p>
                </div>
              </div>
              <div className="border-b border-rule/70 px-6 py-4">
                <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Flags</p>
                <p className="tnum mt-1.5 text-[12.5px] leading-relaxed text-sienna-deep">
                  SYBIL_RISK_HIGH · CLIQUE_PENALTY_HIGH · COLD_START
                </p>
              </div>
              <p className="prose px-6 py-4 text-[13px] leading-relaxed text-ink-dim">
                Low LCB (0.05), thin evidence. High sybil risk (edge-to-job ratio anomaly). Clique
                penalty triggered: coordinated neighborhood.
              </p>
              </motion.div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------
          MECHANISM
      --------------------------------------------------------------- */}
      <section className="relative border-t border-rule bg-paper-deep/60">
        <div className="mx-auto max-w-[1400px] px-5 py-20 sm:px-8">
          <Reveal>
            <h2 className="font-display max-w-lg text-[2rem] font-semibold tracking-tight text-ink sm:text-[2.4rem]">
              Four signals a Sybil ring can&rsquo;t fake at once.
            </h2>
          </Reveal>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {SIGNALS.map((s, i) => (
              <Reveal key={s.name} delay={i * 0.08}>
                <div className="glass group h-full rounded-[24px] px-6 py-7 transition-transform duration-300 hover:-translate-y-1.5">
                  <s.Icon className="h-9 w-9 stroke-bush text-bush transition-colors duration-300 group-hover:stroke-sienna" />
                  <h3 className="font-display mt-5 text-[17px] font-semibold text-ink">{s.name}</h3>
                  <p className="prose mt-2.5 text-[13.5px] leading-relaxed text-ink-dim">{s.detail}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------
          NAIVE VS PROTECTED — the central proof point, full weight
      --------------------------------------------------------------- */}
      <section className="relative border-t border-rule">
        <div className="mx-auto max-w-[1400px] px-5 py-20 sm:px-8">
          <Reveal>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <h2 className="font-display max-w-xl text-[2rem] font-semibold tracking-tight text-ink sm:text-[2.4rem]">
                Same nine agents. Only the gate differs.
              </h2>
              <Link
                href="/naive-vs-protected"
                className="text-[13.5px] font-medium text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna"
              >
                Full breakdown →
              </Link>
            </div>
          </Reveal>

          <div className="mt-10 grid gap-5 lg:grid-cols-2">
            <Reveal delay={0.05}>
              <div className="glass h-full rounded-[28px] px-8 py-9">
                <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-ink-faint">
                  Naive, nothing blocked
                </p>
                <p className="tnum mt-4 text-4xl font-semibold text-ink">
                  {naive.ordersCreated}/{naive.totalAttempts}
                  <span className="ml-2.5 text-[13px] font-normal text-ink-dim">orders created</span>
                </p>
                <div className="mt-5 h-2.5 w-full overflow-hidden rounded-full bg-paper-deep">
                  <div className="h-full rounded-full bg-sienna" style={{ width: "100%" }} />
                </div>
                <p className="tnum mt-4 text-[15px] font-semibold text-sienna-deep">
                  ₹{naive.fraudAtRiskInr} at risk
                </p>
              </div>
            </Reveal>
            <Reveal delay={0.12}>
              <div className="glass h-full rounded-[28px] px-8 py-9">
                <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-ink-faint">
                  Protected, TRACE enforcing
                </p>
                <p className="tnum mt-4 text-4xl font-semibold text-ink">
                  {guarded.ordersCreated}/{guarded.totalAttempts}
                  <span className="ml-2.5 text-[13px] font-normal text-ink-dim">orders created</span>
                </p>
                <div className="mt-5 h-2.5 w-full overflow-hidden rounded-full bg-paper-deep">
                  <div
                    className="h-full rounded-full bg-bush-bright"
                    style={{ width: `${(guarded.ordersCreated / guarded.totalAttempts) * 100}%` }}
                  />
                </div>
                <p className="tnum mt-4 text-[15px] font-semibold text-bush-bright">
                  ₹{guarded.fraudAtRiskInr} at risk
                </p>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------
          BENCHMARK — measured against baselines, ties included
      --------------------------------------------------------------- */}
      <section className="relative border-t border-rule bg-paper-deep/60">
        <div className="mx-auto max-w-[1400px] px-5 py-20 sm:px-8">
          <Reveal>
            <div className="flex flex-wrap items-end justify-between gap-4">
              <h2 className="font-display max-w-xl text-[2rem] font-semibold tracking-tight text-ink sm:text-[2.4rem]">
                Measured against baselines.
              </h2>
              <Link
                href="/outcomes"
                className="text-[13.5px] font-medium text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna"
              >
                Full breakdown →
              </Link>
            </div>
          </Reveal>

          <Reveal delay={0.08}>
            <div className="glass mt-10 rounded-[28px] p-6 sm:p-9">
              <BenchmarkChart />
              <div className="mt-5 flex flex-wrap gap-x-7 gap-y-2 text-[12px] text-ink-dim">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-full bg-bush-bright opacity-50" /> vs
                  behavioral-only
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-full bg-bush-bright" /> vs EigenTrust
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-full bg-sienna" /> tie
                </span>
              </div>
            </div>
          </Reveal>
          <p className="prose mt-5 max-w-lg text-[13px] leading-relaxed text-ink-dim">
            Strategic default ties both baselines, and we&rsquo;re reporting that as measured, not
            leaving it out. TRACE&rsquo;s graph signal has no collusion structure to exploit there yet.
          </p>
        </div>
      </section>

      {/* ---------------------------------------------------------------
          CLOSE — one CTA, pricing mentioned inline, not mirrored
      --------------------------------------------------------------- */}
      <section className="relative border-t border-rule">
        <div className="mx-auto max-w-[1400px] px-5 py-20 sm:px-8">
          <Reveal>
            <div className="glass flex flex-col items-start gap-7 overflow-hidden rounded-[32px] px-8 py-11 sm:flex-row sm:items-center sm:justify-between sm:px-12">
              <p className="prose max-w-lg text-[16px] leading-relaxed text-ink">
                Run a purchase against the live scoring engine. A clean track record unlocks{" "}
                <Link href="/pricing" className="text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna">
                  better pricing on the next one
                </Link>
                .
              </p>
              <Link
                href="/try-it"
                className="group inline-flex shrink-0 items-center gap-2 rounded-full bg-bush px-7 py-3.5 text-[14.5px] font-semibold text-paper shadow-[0_14px_30px_-12px_rgba(31,61,44,0.55)] transition-all hover:-translate-y-0.5 hover:shadow-[0_20px_38px_-14px_rgba(31,61,44,0.6)]"
              >
                Try it live
                <span className="transition-transform group-hover:translate-x-1">→</span>
              </Link>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
