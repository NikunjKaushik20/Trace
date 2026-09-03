import type { Metadata } from "next";
import { BENCHMARKS, SCALED_RUN } from "../lib/data";
import { BenchmarkChart } from "../components/BenchmarkChart";
import { Reveal } from "../components/Reveal";

export const metadata: Metadata = {
  title: "Measured Outcomes",
  description:
    "TRACE benchmarked against behavioral-only scoring and EigenTrust, plus a 36-agent scaled run, including the one scenario where TRACE ties rather than wins.",
};

export default function OutcomesPage() {
  return (
    <section className="relative">
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold tracking-tight text-ink sm:text-[3rem]">
            Where it wins, and where it doesn&rsquo;t, yet.
          </h1>
        </Reveal>

        <Reveal delay={0.06}>
          <h2 className="font-display mt-14 text-[1.4rem] font-semibold text-ink">
            Vs. behavioral-only / vs. EigenTrust
          </h2>
          <div className="glass mt-5 rounded-[28px] p-6 sm:p-9">
            <BenchmarkChart />
          </div>
          <div className="glass mt-5 overflow-x-auto rounded-[24px]">
            <table className="w-full min-w-[480px] border-collapse text-[13.5px]">
              <thead>
                <tr className="border-b border-rule/70 bg-paper-deep/50 text-left text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                  <th className="px-5 py-3 font-semibold">Scenario</th>
                  <th className="px-5 py-3 font-semibold">Vs behavioral</th>
                  <th className="px-5 py-3 font-semibold">Vs EigenTrust</th>
                </tr>
              </thead>
              <tbody>
                {BENCHMARKS.map((b) => (
                  <tr key={b.scenario} className="border-b border-rule/70 last:border-none">
                    <td className="px-5 py-3 text-ink">{b.label}</td>
                    <td className={`tnum px-5 py-3 ${b.tie ? "text-sienna-deep" : "font-semibold text-bush-bright"}`}>
                      {b.behavioral}%
                    </td>
                    <td className={`tnum px-5 py-3 ${b.tie ? "text-sienna-deep" : "font-semibold text-bush-bright"}`}>
                      {b.eigentrust}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="prose mt-4 max-w-lg text-[12.5px] leading-relaxed text-ink-dim">
            Strategic default: TRACE ties both baselines at this scale. The graph signal (PPR,
            Sybil/clique) has no collusion structure to exploit there, so it reduces to
            default-risk detection alone, where the approaches converge. We report that as measured.
          </p>
        </Reveal>

        <Reveal delay={0.12}>
          <h2 className="font-display mt-16 text-[1.4rem] font-semibold text-ink">
            Scaled run: 36 agents, real Razorpay orders
          </h2>
          <div className="mt-5 grid gap-4 sm:grid-cols-4">
            <div className="glass rounded-[24px] px-5 py-6">
              <p className="tnum text-3xl font-semibold text-bush-bright">
                {SCALED_RUN.falsePositives}/{SCALED_RUN.honestAgentsCleared}
              </p>
              <p className="mt-1.5 text-[11.5px] text-ink-dim">honest agents wrongly blocked</p>
            </div>
            <div className="glass rounded-[24px] px-5 py-6">
              <p className="tnum text-3xl font-semibold text-bush-bright">
                {SCALED_RUN.fraudCaught}/{SCALED_RUN.fraudPopulation}
              </p>
              <p className="mt-1.5 text-[11.5px] text-ink-dim">fraud agents caught</p>
            </div>
            <div className="glass rounded-[24px] px-5 py-6">
              <p className="tnum text-3xl font-semibold text-ink">
                {SCALED_RUN.latencyMs.p50}
                <span className="text-[13px] font-normal text-ink-dim">ms</span>
              </p>
              <p className="mt-1.5 text-[11.5px] text-ink-dim">p50 latency, full round trip</p>
            </div>
            <div className="glass rounded-[24px] px-5 py-6">
              <p className="tnum text-3xl font-semibold text-ink">
                {SCALED_RUN.latencyMs.p99}
                <span className="text-[13px] font-normal text-ink-dim">ms</span>
              </p>
              <p className="mt-1.5 text-[11.5px] text-ink-dim">p99 latency</p>
            </div>
          </div>
          <p className="prose mt-4 max-w-lg text-[12.5px] leading-relaxed text-ink-dim">
            {SCALED_RUN.honestAgents} honest agents, a {SCALED_RUN.sybilAgents}-member Sybil ring,{" "}
            and {SCALED_RUN.defectorAgents} strategic defector. {SCALED_RUN.totalEvents} events
            seeded in {SCALED_RUN.seedingSeconds}s against a real 120/minute rate limit, not
            simulated.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
