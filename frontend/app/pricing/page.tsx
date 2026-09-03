import type { Metadata } from "next";
import { CATALOG } from "../lib/data";
import { Reveal } from "../components/Reveal";

export const metadata: Metadata = {
  title: "Growth & Pricing",
  description:
    "Trust-gated pricing tiers: a clean track record unlocks better per-credit rates, and now actually pays for it at checkout, not just on this page.",
};

const TIER_KICKER = ["Base tier", "Mid tier", "Top tier"];

export default function PricingPage() {
  return (
    <section className="relative">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="blob blob-oak opacity-70" />
      </div>
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold tracking-tight text-ink sm:text-[3rem]">
            Better pricing, earned.
          </h1>
          <p className="prose mt-4 max-w-xl text-[15px] leading-relaxed text-ink-dim">
            Every purchase is scored. Request a tier by name on{" "}
            <a href="/try-it" className="text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna">
              Try It
            </a>{" "}
            and it&rsquo;s charged at that tier&rsquo;s real price, gated on that tier&rsquo;s own
            trust requirement. Or turn on auto-upsell and let the merchant apply the best bundle a
            live score already qualifies for.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-5 sm:grid-cols-3">
          {CATALOG.map((tier, i) => (
            <Reveal key={tier.name} delay={i * 0.08}>
              <div
                className={`glass flex h-full flex-col gap-3 rounded-[28px] px-7 py-9 ${
                  i === 1 ? "ring-1 ring-sienna/25" : ""
                }`}
              >
                <span className="text-[11px] font-semibold uppercase tracking-[0.13em] text-ink-faint">
                  {TIER_KICKER[i]}
                </span>
                <h2 className="font-display text-2xl font-semibold text-ink">{tier.name}</h2>
                <p className="tnum text-4xl font-semibold text-ink">
                  ₹{(tier.priceInr / tier.credits).toFixed(0)}
                  <span className="text-[13px] font-normal text-ink-dim"> / credit</span>
                </p>
                <p className="tnum text-[12.5px] text-ink-faint">
                  {tier.credits} credits · ₹{tier.priceInr} total
                </p>
                <p className="mt-2 text-[13px] font-medium text-teal">{tier.requirement}</p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.3}>
          <p className="prose mt-7 max-w-lg text-[12.5px] leading-relaxed text-ink-dim">
            Pro&rsquo;s 20-credit bundle sits exactly at the merchant&rsquo;s hard per-transaction
            cap. The growth incentive and the bounded ceiling meet at the same number, by design.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
