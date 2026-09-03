"use client";

import { useEffect, useState } from "react";
import Script from "next/script";
import { motion, AnimatePresence } from "motion/react";
import { Reveal } from "../components/Reveal";

const API_BASE = process.env.NEXT_PUBLIC_MERCHANT_API_URL ?? "http://localhost:8100";
// Only needed if the merchant has BUILDATHON_MERCHANT_API_KEYS configured
// (see buildathon/.env.example) -- unset by default, matching the
// merchant's own open-by-default local-dev posture. A NEXT_PUBLIC_ value
// ships in client-side JS, so for a public demo page this is an
// access-log/intent signal, not a real secret.
const API_KEY = process.env.NEXT_PUBLIC_MERCHANT_API_KEY;

type PurchaseResult = {
  status: "order_created" | "order_creation_failed" | "blocked";
  agent_id: string;
  amount_inr: number;
  routing_decision: string;
  would_allow: boolean;
  enforced: boolean;
  score: number;
  flags: string[];
  explanation: string;
  razorpay_order_id: string | null;
  job_id: string;
  latency_ms: number;
  unlocked_tier: string | null;
  next_tier_hint: { tier: string; min_trust_score: number; score_gap: number } | null;
  // Real upsell/cross-sell decision (see buildathon/NOTES.md #9) -- what
  // this specific purchase actually charged, price-wise.
  requested_tier: string | null;
  applied_tier: string | null;
  upsell_applied: boolean;
  upsell_note: string | null;
};

const SAMPLE_AGENTS = ["agent_honest_0", "agent_defector_0", "agent_sybil_0"];
const TIER_NAMES = ["Starter", "Plus", "Pro"] as const;
// A tier is a fixed bundle: selecting one replaces the free-form credit
// count entirely (see merchant/app.py's _resolve_initial_terms). The
// credits field is disabled while a tier is active and shows that bundle's
// real size so the number on screen always matches what gets charged.
const TIER_CREDITS: Record<string, number> = { Starter: 1, Plus: 5, Pro: 20 };

type HistoryEntry = { at: number; agentId: string; result: PurchaseResult };

// -- Razorpay Checkout.js: a hosted payment screen, not an npm package --
// loaded via <Script>, exposing a global constructor. This is the piece
// that was missing before: /buy-credits only ever proved an order was
// *created* (a server-to-server Razorpay API call); this is the actual
// screen a buyer pays through, and the signature-verified confirmation
// that a payment was *captured*, not just attempted.
type RazorpayCheckoutResponse = {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
};
type RazorpayOptions = {
  key: string;
  amount: number;
  currency: string;
  order_id: string;
  name: string;
  description: string;
  prefill?: { name?: string };
  theme?: { color?: string };
  handler: (response: RazorpayCheckoutResponse) => void;
  modal?: { ondismiss?: () => void };
};
type RazorpayInstance = { open: () => void };
declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => RazorpayInstance;
  }
}

type PaymentState =
  | { phase: "idle" }
  | { phase: "opening" }
  | { phase: "verifying" }
  | { phase: "captured"; paymentId: string }
  | { phase: "verification_failed" }
  | { phase: "dismissed" };

export default function TryItForm() {
  const [agentId, setAgentId] = useState("agent_honest_0");
  const [credits, setCredits] = useState(1);
  const [tier, setTier] = useState<string | null>(null);
  const [autoUpsell, setAutoUpsell] = useState(false);
  const [result, setResult] = useState<PurchaseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [checkoutReady, setCheckoutReady] = useState(false);
  const [razorpayConfig, setRazorpayConfig] = useState<{ keyId: string | null; enabled: boolean } | null>(null);
  const [payment, setPayment] = useState<PaymentState>({ phase: "idle" });

  useEffect(() => {
    fetch(`${API_BASE}/razorpay-config`)
      .then((r) => r.json())
      .then((body) => setRazorpayConfig({ keyId: body.key_id, enabled: body.enabled }))
      .catch(() => setRazorpayConfig({ keyId: null, enabled: false }));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    setPayment({ phase: "idle" });
    try {
      const res = await fetch(`${API_BASE}/buy-credits`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}),
        },
        body: JSON.stringify({
          agent_id: agentId,
          credits,
          ...(tier ? { tier } : { auto_upsell: autoUpsell }),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Request failed (${res.status})`);
      }
      const data: PurchaseResult = await res.json();
      setResult(data);
      setHistory((h) => [{ at: Date.now(), agentId, result: data }, ...h].slice(0, 8));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the merchant API. Is it running?");
    } finally {
      setLoading(false);
    }
  }

  function openCheckout() {
    if (!result?.razorpay_order_id || !razorpayConfig?.keyId || !window.Razorpay) return;
    setPayment({ phase: "opening" });
    const rzp = new window.Razorpay({
      key: razorpayConfig.keyId,
      amount: Math.round(result.amount_inr * 100),
      currency: "INR",
      order_id: result.razorpay_order_id,
      name: "TRACE Demo Merchant",
      description: `${credits} GPU inference credit${credits === 1 ? "" : "s"}`,
      prefill: { name: result.agent_id },
      theme: { color: "#a94e28" },
      handler: async (response) => {
        setPayment({ phase: "verifying" });
        try {
          const res = await fetch(`${API_BASE}/verify-payment`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(response),
          });
          const body = await res.json();
          if (res.ok && body.verified) {
            setPayment({ phase: "captured", paymentId: body.razorpay_payment_id });
          } else {
            setPayment({ phase: "verification_failed" });
          }
        } catch {
          setPayment({ phase: "verification_failed" });
        }
      },
      modal: { ondismiss: () => setPayment({ phase: "dismissed" }) },
    });
    rzp.open();
  }

  const allowed = result?.status === "order_created";

  return (
    <section className="relative">
      {/* Razorpay's hosted checkout script -- an external, Razorpay-served
          script, the same one their own integration docs have every
          merchant load. Not bundled: it has to come from Razorpay so the
          payment screen it opens is genuinely theirs. */}
      <Script
        src="https://checkout.razorpay.com/v1/checkout.js"
        strategy="afterInteractive"
        onLoad={() => setCheckoutReady(true)}
      />
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="blob blob-teal opacity-40" />
      </div>
      <div className="mx-auto max-w-[1400px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold tracking-tight text-ink sm:text-[3rem]">
            Score a purchase, live.
          </h1>
          <p className="prose mt-4 max-w-xl text-[15px] leading-relaxed text-ink-dim">
            This calls the real scoring engine, not a mock. An allowed purchase creates a real
            Razorpay test-mode order, and you can actually pay it, right here, through
            Razorpay&rsquo;s own checkout screen.
          </p>
        </Reveal>

        <Reveal delay={0.08}>
          <form onSubmit={submit} className="glass mt-10 flex flex-wrap items-end gap-5 rounded-[28px] p-6 sm:p-7">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="agent" className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                Agent ID
              </label>
              <input
                id="agent"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                list="sample-agents"
                className="rounded-xl border border-rule bg-panel/70 px-3.5 py-2.5 text-[13.5px] text-ink outline-none transition-colors focus-visible:border-sienna"
              />
              <datalist id="sample-agents">
                {SAMPLE_AGENTS.map((a) => (
                  <option key={a} value={a} />
                ))}
              </datalist>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="credits" className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                Credits
              </label>
              <input
                id="credits"
                type="number"
                min={1}
                value={tier ? TIER_CREDITS[tier] : credits}
                disabled={!!tier}
                onChange={(e) => setCredits(Number(e.target.value))}
                className="w-24 rounded-xl border border-rule bg-panel/70 px-3.5 py-2.5 text-[13.5px] text-ink outline-none transition-colors focus-visible:border-sienna disabled:cursor-not-allowed disabled:opacity-40"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                Tier (optional)
              </span>
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => setTier(null)}
                  className={`rounded-full border px-3 py-2 text-[12px] font-medium transition-colors ${
                    tier === null
                      ? "border-sienna bg-sienna-bg text-sienna-deep"
                      : "border-rule text-ink-dim hover:border-rule-strong"
                  }`}
                >
                  flat rate
                </button>
                {TIER_NAMES.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTier(t)}
                    className={`rounded-full border px-3 py-2 text-[12px] font-medium transition-colors ${
                      tier === t
                        ? "border-sienna bg-sienna-bg text-sienna-deep"
                        : "border-rule text-ink-dim hover:border-rule-strong"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
            <label className={`flex items-center gap-2 pb-2.5 text-[12.5px] ${tier ? "opacity-40" : "text-ink-dim"}`}>
              <input
                type="checkbox"
                checked={autoUpsell}
                disabled={!!tier}
                onChange={(e) => setAutoUpsell(e.target.checked)}
                className="h-4 w-4 accent-bush"
              />
              auto-upsell
            </label>
            <button
              type="submit"
              disabled={loading}
              className="ml-auto inline-flex items-center gap-2 rounded-full bg-bush px-7 py-3 text-[13.5px] font-semibold text-paper shadow-[0_14px_30px_-14px_rgba(31,61,44,0.55)] transition-all hover:-translate-y-0.5 disabled:translate-y-0 disabled:opacity-50"
            >
              {loading ? "Scoring…" : "Buy credits"}
            </button>
          </form>
        </Reveal>

        <AnimatePresence mode="wait">
          {error && (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="glass mt-6 rounded-[24px] border-sienna/20 bg-sienna-bg/70 px-6 py-5 text-[13.5px] text-sienna-deep"
            >
              <p className="font-semibold">Could not score this purchase.</p>
              <p className="prose mt-1.5 text-[12.5px] opacity-90">
                {error} Start the merchant locally with{" "}
                <code className="tnum">python -m buildathon.demo.demo_runner</code> or point{" "}
                <code className="tnum">NEXT_PUBLIC_MERCHANT_API_URL</code> at a running instance.
              </p>
            </motion.div>
          )}

          {result && (
            <motion.div
              key="result"
              initial={{ opacity: 0, y: 14, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              className="glass mt-6 overflow-hidden rounded-[28px]"
            >
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule/70 bg-paper-deep/40 px-6 py-4">
                <span
                  className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-[12.5px] font-semibold ${
                    allowed ? "bg-bush-bg text-bush-bright" : "bg-sienna-bg text-sienna-deep"
                  }`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${allowed ? "bg-bush-bright" : "bg-sienna-deep"}`} />
                  {result.status.replace(/_/g, " ")}
                </span>
                <span className="text-[12.5px] text-ink-dim">{result.routing_decision}</span>
              </div>
              <div className="grid grid-cols-3 divide-x divide-rule/70 border-b border-rule/70">
                <div className="px-6 py-5">
                  <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Score</p>
                  <p className="tnum mt-1 text-xl font-semibold text-ink">{result.score.toFixed(2)}</p>
                </div>
                <div className="px-6 py-5">
                  <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Amount</p>
                  <p className="tnum mt-1 text-xl font-semibold text-ink">₹{result.amount_inr}</p>
                </div>
                <div className="px-6 py-5">
                  <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Latency</p>
                  <p className="tnum mt-1 text-xl font-semibold text-ink">{result.latency_ms.toFixed(1)}ms</p>
                </div>
              </div>
              {result.flags.length > 0 && (
                <div className="border-b border-rule/70 px-6 py-4">
                  <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Flags</p>
                  <p className="tnum mt-1.5 text-[12.5px] text-sienna-deep">{result.flags.join(" · ")}</p>
                </div>
              )}
              <div className="prose border-b border-rule/70 px-6 py-4 text-[13.5px] leading-relaxed text-ink-dim">
                {result.explanation}
              </div>
              {result.upsell_applied && (
                <div className="border-b border-rule/70 bg-bush-bg/60 px-6 py-4">
                  <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">
                    Auto-upsold to {result.applied_tier?.toUpperCase()}
                  </p>
                  <p className="prose mt-1 text-[12.5px] text-bush-bright">{result.upsell_note}</p>
                </div>
              )}
              {result.applied_tier && !result.upsell_applied && (
                <div className="border-b border-rule/70 px-6 py-4">
                  <p className="text-[12.5px] text-ink-dim">
                    Charged at <span className="font-medium text-ink">{result.applied_tier}</span> tier
                    pricing, as requested.
                  </p>
                </div>
              )}
              {result.unlocked_tier && (
                <div className={`px-6 py-4 ${result.razorpay_order_id ? "border-b border-rule/70" : ""}`}>
                  <p className="prose text-[12.5px] text-ink-dim">
                    Unlocks the <span className="font-medium text-ink">{result.unlocked_tier}</span> pricing
                    tier.
                    {result.next_tier_hint &&
                      ` ${result.next_tier_hint.score_gap.toFixed(2)} away from ${result.next_tier_hint.tier}.`}
                  </p>
                </div>
              )}

              {/* The piece that was missing: an order_created response only
                  ever proved a Razorpay order object exists server-side.
                  This is where a buyer actually pays it. */}
              {result.razorpay_order_id && (
                <div className="px-6 py-5">
                  {payment.phase === "idle" || payment.phase === "opening" ? (
                    razorpayConfig?.enabled ? (
                      <button
                        type="button"
                        onClick={openCheckout}
                        disabled={!checkoutReady || payment.phase === "opening"}
                        className="inline-flex items-center gap-2 rounded-full bg-sienna px-6 py-2.5 text-[13px] font-semibold text-paper shadow-[0_10px_24px_-12px_rgba(122,52,24,0.55)] transition-all hover:-translate-y-0.5 disabled:translate-y-0 disabled:opacity-50"
                      >
                        {checkoutReady ? `Pay ₹${result.amount_inr} with Razorpay →` : "Loading Razorpay…"}
                      </button>
                    ) : (
                      <p className="prose text-[12.5px] text-ink-faint">
                        Razorpay Checkout isn&rsquo;t configured on this merchant instance, so the order was
                        created but there&rsquo;s no key to open a payment screen with. It can still be paid
                        from the Razorpay dashboard (Test Mode → Orders).
                      </p>
                    )
                  ) : payment.phase === "verifying" ? (
                    <p className="tnum text-[13px] text-ink-dim">Verifying payment signature…</p>
                  ) : payment.phase === "captured" ? (
                    <div className="rounded-2xl bg-bush-bg px-4 py-3">
                      <p className="text-[12.5px] font-semibold text-bush-bright">
                        Payment captured. This money actually moved.
                      </p>
                      <p className="tnum mt-1 text-[11.5px] text-bush-bright/80">payment_id: {payment.paymentId}</p>
                    </div>
                  ) : payment.phase === "verification_failed" ? (
                    <div className="rounded-2xl bg-sienna-bg px-4 py-3">
                      <p className="text-[12.5px] font-semibold text-sienna-deep">
                        Payment signature didn&rsquo;t verify, so it wasn&rsquo;t recorded as captured. Try
                        again, or check that the merchant is running with a matching Razorpay key pair.
                      </p>
                    </div>
                  ) : (
                    <div className="rounded-2xl bg-paper-deep px-4 py-3">
                      <p className="text-[12.5px] text-ink-dim">
                        Checkout closed without completing payment. The order still exists; nothing was charged.
                      </p>
                      <button
                        type="button"
                        onClick={openCheckout}
                        className="mt-2 text-[12.5px] font-medium text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna"
                      >
                        Try again →
                      </button>
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {history.length > 0 && (
          <div className="mt-12">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
              Session history: {history.length} attempt{history.length === 1 ? "" : "s"}
            </p>
            <div className="glass mt-3 overflow-hidden rounded-[24px]">
              {history.map((h, i) => (
                <div
                  key={h.at}
                  className={`flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-[12.5px] ${
                    i !== history.length - 1 ? "border-b border-rule/70" : ""
                  }`}
                >
                  <span className="tnum text-ink-dim">{h.agentId}</span>
                  <span className={h.result.status === "order_created" ? "text-bush-bright" : "text-sienna-deep"}>
                    {h.result.status.replace(/_/g, " ")}
                  </span>
                  <span className="tnum text-ink-dim">{h.result.score.toFixed(2)}</span>
                  <span className="text-ink-dim">{h.result.routing_decision}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
