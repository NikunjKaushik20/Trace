import type { Metadata } from "next";
import { Reveal } from "../components/Reveal";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "The plain-language terms for using TRACE's demo site.",
};

export default function TermsPage() {
  return (
    <section className="relative">
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold tracking-tight text-ink sm:text-[3rem]">
            Terms of Service
          </h1>
          <p className="prose mt-4 max-w-xl text-[13.5px] text-ink-faint">Last updated August 2026.</p>
        </Reveal>

        <Reveal delay={0.06}>
          <div className="prose mt-10 max-w-2xl space-y-6 text-[14.5px] leading-relaxed text-ink-dim">
            <p>
              TRACE, as shown here, is a working demonstration of a trust-scoring engine for
              agent-to-agent commerce. It&rsquo;s provided as-is, so it can go down, get rebuilt, or
              change shape without notice.
            </p>
            <div>
              <h2 className="font-display text-[1.15rem] font-semibold text-ink">Test-mode only</h2>
              <p className="mt-2">
                Every order this site creates runs against Razorpay test-mode credentials. The
                merchant backend hard-refuses to start against a live key, so no real payment can
                move through Try It Live, no matter what you enter at checkout.
              </p>
            </div>
            <div>
              <h2 className="font-display text-[1.15rem] font-semibold text-ink">The numbers on this site</h2>
              <p className="mt-2">
                Every score, ratio, and dollar figure shown here traces back to an actual run of the
                real scoring engine. None of it is invented for effect, and where a result is a tie
                or a limitation rather than a win, it&rsquo;s shown as one.
              </p>
            </div>
            <div>
              <h2 className="font-display text-[1.15rem] font-semibold text-ink">No warranty</h2>
              <p className="mt-2">
                This site and the scoring behind it are offered without any warranty, express or
                implied. Don&rsquo;t rely on it to gate real money without doing your own review
                first.
              </p>
            </div>
            <div>
              <h2 className="font-display text-[1.15rem] font-semibold text-ink">Contact</h2>
              <p className="mt-2">
                Questions about these terms can go to{" "}
                <a
                  href="https://linkedin.com/in/nikunjkaushik2005"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna"
                >
                  LinkedIn
                </a>
                .
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
