import type { Metadata } from "next";
import { Reveal } from "../components/Reveal";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "What TRACE's demo site collects, and what it doesn't.",
};

export default function PrivacyPage() {
  return (
    <section className="relative">
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold tracking-tight text-ink sm:text-[3rem]">
            Privacy Policy
          </h1>
          <p className="prose mt-4 max-w-xl text-[13.5px] text-ink-faint">Last updated August 2026.</p>
        </Reveal>

        <Reveal delay={0.06}>
          <div className="prose mt-10 max-w-2xl space-y-6 text-[14.5px] leading-relaxed text-ink-dim">
            <p>
              This site doesn&rsquo;t use tracking cookies, analytics scripts, or ad pixels. There
              are no accounts to sign up for and nothing to log in to, so there&rsquo;s no profile of
              you being built anywhere on our side.
            </p>
            <div>
              <h2 className="font-display text-[1.15rem] font-semibold text-ink">What Try It Live sends</h2>
              <p className="mt-2">
                The agent ID and credit amount you enter on the Try It Live page are sent to the
                TRACE scoring API to compute a real trust score. That request isn&rsquo;t tied to your
                identity in any way, since an agent ID is just a label you typed in, not an account.
              </p>
            </div>
            <div>
              <h2 className="font-display text-[1.15rem] font-semibold text-ink">What Razorpay sees</h2>
              <p className="mt-2">
                If you go on to pay a created order, Razorpay&rsquo;s own checkout screen opens and
                handles your payment details directly. We never see or store your card number, UPI
                ID, or bank details; Razorpay processes those under its own privacy policy. Every
                credential this site runs against is test-mode by design, and it refuses to start
                against a live key at all.
              </p>
            </div>
            <div>
              <h2 className="font-display text-[1.15rem] font-semibold text-ink">Fonts</h2>
              <p className="mt-2">
                The typefaces on this page are bundled at build time, not loaded from a third-party
                font service at runtime, so visiting this site doesn&rsquo;t send a request to Google
                or anyone else just to render text.
              </p>
            </div>
            <div>
              <h2 className="font-display text-[1.15rem] font-semibold text-ink">Questions</h2>
              <p className="mt-2">
                Reach out on{" "}
                <a
                  href="https://linkedin.com/in/nikunjkaushik2005"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna"
                >
                  LinkedIn
                </a>{" "}
                if anything here is unclear.
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
