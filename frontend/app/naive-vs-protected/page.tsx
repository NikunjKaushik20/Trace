import type { Metadata } from "next";
import { NAIVE_VS_PROTECTED, PROTECTED_RUN } from "../lib/data";
import { ProtectedPassTable } from "./ProtectedPassTable";
import { Reveal } from "../components/Reveal";

export const metadata: Metadata = {
  title: "Naive vs. Protected",
  description:
    "The same nine agents, the same history, only the enforcement toggle differs: ₹600 at risk with no gate, ₹0 with TRACE enforcing.",
};

export default function NaiveVsProtectedPage() {
  const { naive, protected: guarded } = NAIVE_VS_PROTECTED;

  return (
    <section className="relative">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="blob blob-sienna opacity-60" />
      </div>
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold tracking-tight text-ink sm:text-[3rem]">
            Same agents. Same history. Only the gate differs.
          </h1>
          <p className="prose mt-4 max-w-xl text-[15px] leading-relaxed text-ink-dim">
            Nine agents: three honest, one strategic defector, and a five-node Sybil ring, all run
            through identical scoring twice. Once with enforcement off, once on.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-5 lg:grid-cols-2">
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

        <Reveal delay={0.15}>
          <h2 className="font-display mt-16 text-[1.4rem] font-semibold text-ink">
            Protected pass: every decision
          </h2>
          <p className="prose mt-2 max-w-lg text-[13px] text-ink-dim">
            Click a row for its flags and full explanation.
          </p>
          <div className="mt-5">
            <ProtectedPassTable rows={PROTECTED_RUN} />
          </div>
        </Reveal>
      </div>
    </section>
  );
}
