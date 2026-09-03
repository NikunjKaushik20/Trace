import type { Metadata } from "next";
import { PROTECTED_RUN } from "../lib/data";
import { AgentTable } from "./AgentTable";
import { TrustRoots } from "../components/TrustRoots";
import { Reveal } from "../components/Reveal";

export const metadata: Metadata = {
  title: "Marketplace",
  description: "Every simulated agent in the population: class, score, decision, and flags.",
};

export default function MarketplacePage() {
  return (
    <section className="relative">
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold tracking-tight text-ink sm:text-[3rem]">
            The population, in full.
          </h1>
          <p className="prose mt-4 max-w-xl text-[15px] leading-relaxed text-ink-dim">
            Nine agents. Three build a real, diverse purchase history. One builds a clean record,
            then defects sharply. Five vouch for each other densely while completing almost
            nothing real.
          </p>
        </Reveal>

        <Reveal delay={0.08}>
          <div className="glass relative mt-10 overflow-hidden rounded-[28px] px-6 py-8 sm:px-10">
            <TrustRoots className="mx-auto w-full max-w-2xl" />
            <p className="prose mx-auto mt-2 max-w-md text-center text-[12.5px] leading-relaxed text-ink-faint">
              Personalized PageRank flowing outward from honest seeds (
              <code className="tnum text-[11.5px]">api/graph.py</code>), the graph trust signal
              scored into every decision below. The Sybil ring at the edge sits structurally
              disconnected: no path in, no trust to inherit.
            </p>
          </div>
        </Reveal>

        <Reveal delay={0.1}>
          <p className="prose mt-14 text-[12.5px] text-ink-dim">Click a row for its full explanation.</p>
          <div className="mt-3">
            <AgentTable rows={PROTECTED_RUN} />
          </div>
        </Reveal>

        <Reveal delay={0.14}>
          <p className="prose mt-6 max-w-lg text-[12.5px] leading-relaxed text-ink-dim">
            The directory above uses this session&rsquo;s captured population data. The live trust
            graph endpoint (<code className="tnum text-[11.5px]">GET /v1/graph</code>) now reads
            each node&rsquo;s real, persisted PageRank score from{" "}
            <code className="tnum text-[11.5px]">GraphScore</code>, computed by the same worker
            that scores live purchases. Not a placeholder.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
