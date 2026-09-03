import type { Metadata } from "next";
import { Reveal } from "../components/Reveal";

export const metadata: Metadata = {
  title: "About",
  description: "Why TRACE exists, how it works, and who built it.",
};

export default function AboutPage() {
  return (
    <section className="relative">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="blob blob-teal opacity-30" />
      </div>
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold tracking-tight text-ink sm:text-[3rem]">
            Built for a world where agents buy things.
          </h1>
          <p className="prose mt-4 max-w-xl text-[15px] leading-relaxed text-ink-dim">
            AI agents are starting to make purchases on their own: buying compute, hiring other
            agents, paying for data. None of them have a credit history. TRACE is a first attempt
            at giving a merchant a real, explainable answer to &ldquo;should I trust this buyer,&rdquo;
            computed from what an agent has actually done, not what it claims about itself.
          </p>
        </Reveal>

        <Reveal delay={0.06}>
          <div className="glass mt-10 max-w-2xl rounded-[28px] px-8 py-9">
            <h2 className="font-display text-[1.3rem] font-semibold text-ink">How it thinks about trust</h2>
            <p className="prose mt-3 text-[13.5px] leading-relaxed text-ink-dim">
              A Bayesian lower confidence bound instead of a raw success rate, so a thin history
              reads as uncertain rather than clean. A CUSUM change-point detector that catches a
              sudden shift in behavior and doesn&rsquo;t let it fade back into a good average.
              Personalized PageRank over the transaction graph, so trust has to travel through real,
              completed work rather than being claimed. All three feed one score, and the score
              always comes with the reasons behind it.
            </p>
          </div>
        </Reveal>

        <Reveal delay={0.12}>
          <div className="mt-10 max-w-2xl">
            <h2 className="font-display text-[1.3rem] font-semibold text-ink">Who&rsquo;s behind it</h2>
            <p className="prose mt-3 text-[13.5px] leading-relaxed text-ink-dim">
              TRACE is built and maintained by Nikunj Kaushik, who writes and ships every part of
              it: the scoring engine, the API, and this site. If you want to talk about it, find me
              on{" "}
              <a
                href="https://linkedin.com/in/nikunjkaushik2005"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna"
              >
                LinkedIn
              </a>
              , or read the source on{" "}
              <a
                href="https://github.com/NikunjKaushik20/TRACE-API"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna"
              >
                GitHub
              </a>
              .
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
