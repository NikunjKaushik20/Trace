import type { Metadata } from "next";
import { WeightChart } from "../components/WeightChart";
import { Reveal } from "../components/Reveal";

export const metadata: Metadata = {
  title: "Audit & Governance",
  description:
    "How a score is composed, what's verified vs. in progress, and what's deliberately not claimed.",
};

export default function AuditPage() {
  return (
    <section className="relative">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="blob blob-bush opacity-50" />
      </div>
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold tracking-tight text-ink sm:text-[3rem]">
            Nothing here is a black box.
          </h1>
        </Reveal>

        <Reveal delay={0.06}>
          <h2 className="font-display mt-14 text-[1.4rem] font-semibold text-ink">Score composition</h2>
          <p className="prose mt-2 max-w-lg text-[13px] leading-relaxed text-ink-dim">
            Real weight constants from <code className="tnum text-[12px]">api/scorer.py</code>&rsquo;s
            formula: how much each signal counts, not one decision&rsquo;s computed values (the API
            doesn&rsquo;t expose those, only the final score).
          </p>
          <div className="mt-5">
            <WeightChart />
          </div>
        </Reveal>

        <div className="mt-14 grid gap-5 sm:grid-cols-2">
          <Reveal delay={0.1}>
            <div className="glass h-full rounded-[28px] px-7 py-8">
              <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-bush-bright">
                Verified, live in production
              </p>
              <ul className="prose mt-4 space-y-3 text-[13.5px] leading-relaxed text-ink-dim">
                <li>
                  Bayesian confidence bound, change-point detection, graph trust, and Sybil/clique
                  penalty are all real and unit-tested.
                </li>
                <li>
                  A CUSUM persistence bug: found, root-caused, fixed with a database migration,
                  verified column-by-column in production.
                </li>
                <li>
                  A concurrency race in provider-state updates: found, fixed with atomic
                  increments, verified under concurrent load.
                </li>
              </ul>
            </div>
          </Reveal>
          <Reveal delay={0.16}>
            <div className="glass h-full rounded-[28px] px-7 py-8">
              <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-sienna-deep">
                Stated plainly, not hidden
              </p>
              <ul className="prose mt-4 space-y-3 text-[13.5px] leading-relaxed text-ink-dim">
                <li>The audit hash shown on a score is a local SHA-256 digest, not an on-chain anchor.</li>
                <li>Policy rules can be recorded and listed, but are not yet consumed by live scoring.</li>
                <li>
                  An order being &ldquo;created&rdquo; isn&rsquo;t the same as a payment being
                  &ldquo;captured.&rdquo; Try It Live can now do both: a real Razorpay Checkout
                  screen opens, and a completed payment is verified by signature before it counts
                  as captured.
                </li>
              </ul>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
