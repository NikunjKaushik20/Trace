"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Reveal } from "../components/Reveal";
import {
  HONEST_RUN,
  COMPROMISED_RUN,
  type AgentRun,
  type LedgerEntry,
  type LedgerOutcome,
} from "../lib/agent";

const API_BASE = process.env.NEXT_PUBLIC_MERCHANT_API_URL ?? "http://localhost:8100";

type Mode = "honest" | "compromised";

const OUTCOME_CHIP: Record<LedgerOutcome, string> = {
  allow: "bg-bush-bg text-bush-bright",
  deny: "bg-sienna-bg text-sienna-deep",
  cap: "bg-sienna-bg text-sienna-deep",
  budget: "bg-oak-bg text-ink-dim",
  data: "bg-teal-bg text-teal",
  info: "bg-paper-deep text-ink-dim",
};

const TOOL_LABEL: Record<string, string> = {
  get_catalog: "get_catalog",
  check_trust: "check_trust",
  buy_credits: "buy_credits",
};

// -- raw /agent/run response -> the AgentRun shape lib/agent.ts uses.
// Mirrors buildathon/demo/gen_frontend_agent_data.py so a live run renders
// identically to the captured ones.
type RawResult = Record<string, unknown>;
function classify(name: string, r: RawResult): LedgerEntry["action"] {
  const args = "";
  if (name === "get_catalog") {
    const n = Array.isArray(r.tiers) ? r.tiers.length : 0;
    return { tool: "get_catalog", args, outcome: "info", line: `catalog read — ${n} tiers` };
  }
  if (name === "check_trust") {
    const score = typeof r.score === "number" ? r.score : null;
    const unlocked = typeof r.unlocked_tier === "string" ? r.unlocked_tier : null;
    return {
      tool: "check_trust",
      args,
      outcome: "data",
      line:
        (score != null ? `score ${score.toFixed(2)}` : "trust checked") +
        (r.routing_decision ? ` · ${r.routing_decision}` : "") +
        (unlocked ? ` · unlocks ${unlocked}` : ""),
      detail: typeof r.explanation === "string" ? r.explanation : null,
    };
  }
  if (r.status === "order_created") {
    const tier = typeof r.applied_tier === "string" ? r.applied_tier : null;
    return {
      tool: "buy_credits",
      args,
      outcome: "allow",
      line:
        `order created · ₹${Number(r.amount_inr ?? 0).toFixed(0)} · ${r.routing_decision ?? ""}` +
        (tier ? ` · ${tier} tier` : ""),
      detail: typeof r.explanation === "string" ? r.explanation : null,
    };
  }
  if (r.status === "blocked") {
    const flags = Array.isArray(r.flags) && r.flags.length ? r.flags.join(", ") : String(r.routing_decision ?? "");
    return { tool: "buy_credits", args, outcome: "deny", line: `blocked by TRACE · ${flags}`, detail: String(r.explanation ?? "") };
  }
  if (r.error && r.status_code === 400)
    return { tool: "buy_credits", args, outcome: "cap", line: "rejected (400) · per-purchase cap", detail: String(r.detail ?? "") };
  if (r.error && r.status_code === 429)
    return { tool: "buy_credits", args, outcome: "cap", line: "rejected (429) · rolling velocity cap", detail: String(r.detail ?? "") };
  if (r.refused_client_side)
    return { tool: "buy_credits", args, outcome: "budget", line: "not attempted · would exceed budget", detail: String(r.detail ?? "") };
  return { tool: "buy_credits", args, outcome: "info", line: "ok" };
}

const OUTCOME_MAP: Record<string, { label: string; kind: "allow" | "deny" | "info" }> = {
  goal_met: { label: "Goal met", kind: "allow" },
  budget_exhausted: { label: "Budget spent out", kind: "info" },
  agent_stopped: { label: "Stopped by the caps", kind: "deny" },
  max_turns: { label: "Turn limit reached", kind: "info" },
  llm_unavailable_fallback: { label: "LLM unavailable — safe fallback", kind: "info" },
};

function toRun(raw: RawResult): AgentRun {
  const turns = Array.isArray(raw.turns) ? (raw.turns as RawResult[]) : [];
  const entries: LedgerEntry[] = turns.map((t) => {
    const tools = Array.isArray(t.tools) ? (t.tools as RawResult[]) : [];
    const first = tools[0];
    return {
      turn: Number(t.index ?? 0),
      reasoning: (t.reasoning as string) ?? null,
      action: first ? classify(first.name as string, (first.result ?? {}) as RawResult) : null,
    };
  });
  const buys = turns
    .flatMap((t) => (Array.isArray(t.tools) ? (t.tools as RawResult[]) : []))
    .filter((tl) => tl.name === "buy_credits")
    .map((tl) => (tl.result ?? {}) as RawResult);
  const caps = [...new Set(buys.filter((r) => r.error && [400, 429].includes(Number(r.status_code))).map((r) => Number(r.status_code)))].sort();
  const largest = Math.max(0, ...buys.filter((r) => r.status === "order_created").map((r) => Number(r.amount_inr ?? 0)));
  const cfg = (raw.config ?? {}) as RawResult;
  const om = OUTCOME_MAP[String(raw.outcome)] ?? { label: String(raw.outcome), kind: "info" as const };
  return {
    buyerName: String(cfg.buyer_name ?? ""),
    agentId: String(cfg.agent_id ?? ""),
    goalCredits: Number(cfg.goal_credits ?? 0),
    budgetInr: Number(cfg.budget_inr ?? 0),
    outcome: String(raw.outcome),
    outcomeLabel: om.label,
    outcomeKind: om.kind,
    creditsAcquired: Number(raw.credits_acquired ?? 0),
    spentInr: Number(raw.spent_inr ?? 0),
    orders: Array.isArray(raw.razorpay_orders) ? (raw.razorpay_orders as string[]) : [],
    durationS: Number(raw.duration_s ?? 0),
    entries,
    capsFired: caps,
    largestOrderInr: largest,
  };
}

function Entry({ entry, index, live }: { entry: LedgerEntry; index: number; live: boolean }) {
  const [open, setOpen] = useState(false);
  const a = entry.action;
  return (
    <motion.li
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1], delay: live ? index * 0.22 : index * 0.12 }}
      className="relative border-b border-rule/60 last:border-none"
    >
      <div className="flex gap-4 px-6 py-5 sm:px-8">
        <span className="tnum mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-paper-deep text-[11px] font-semibold text-ink-dim">
          {entry.turn}
        </span>
        <div className="min-w-0 flex-1">
          {entry.reasoning && (
            <p className="prose border-l-2 border-oak/60 pl-3 text-[13.5px] italic leading-relaxed text-ink-dim">
              {entry.reasoning}
            </p>
          )}
          {a ? (
            <div className="mt-3 flex flex-wrap items-center gap-2.5">
              <code className="tnum rounded-lg bg-panel/70 px-2.5 py-1 text-[12px] text-ink">
                → {TOOL_LABEL[a.tool] ?? a.tool}
                {a.args ? `(${a.args})` : "()"}
              </code>
              <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium ${OUTCOME_CHIP[a.outcome]}`}>
                <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
                {a.line}
              </span>
              {a.detail && (
                <button
                  type="button"
                  onClick={() => setOpen((v) => !v)}
                  className="text-[12px] font-medium text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna"
                >
                  {open ? "hide" : "why"}
                </button>
              )}
            </div>
          ) : (
            <p className="mt-3 text-[12px] font-medium uppercase tracking-wide text-ink-faint">
              closing summary
            </p>
          )}
          <AnimatePresence initial={false}>
            {open && a?.detail && (
              <motion.p
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                className="prose mt-2.5 overflow-hidden text-[12.5px] leading-relaxed text-ink-dim"
              >
                {a.detail}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.li>
  );
}

export default function AgentTheatre() {
  const [mode, setMode] = useState<Mode>("honest");
  const [liveEnabled, setLiveEnabled] = useState(false);
  const [liveRun, setLiveRun] = useState<AgentRun | null>(null);
  const [running, setRunning] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [replayKey, setReplayKey] = useState(0);

  useEffect(() => {
    fetch(`${API_BASE}/agent/config`)
      .then((r) => r.json())
      .then((b) => setLiveEnabled(Boolean(b.enabled)))
      .catch(() => setLiveEnabled(false));
  }, []);

  // switching mode or replaying drops any live result and re-triggers the reveal
  useEffect(() => {
    setLiveRun(null);
    setLiveError(null);
  }, [mode]);

  const captured = mode === "honest" ? HONEST_RUN : COMPROMISED_RUN;
  const run = liveRun ?? captured;
  const isLive = liveRun !== null;

  const spentPct = useMemo(
    () => Math.min(100, (run.spentInr / run.budgetInr) * 100),
    [run.spentInr, run.budgetInr],
  );

  async function runLive() {
    setRunning(true);
    setLiveError(null);
    setLiveRun(null);
    try {
      const res = await fetch(`${API_BASE}/agent/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      if (!res.ok) {
        const b = await res.json().catch(() => ({}));
        throw new Error(b.detail ?? `Request failed (${res.status})`);
      }
      setLiveRun(toRun(await res.json()));
      setReplayKey((k) => k + 1);
    } catch (e) {
      setLiveError(e instanceof Error ? e.message : "Could not reach the agent runner.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="blob blob-bush" />
        <div className="blob blob-oak" />
      </div>

      <div className="mx-auto max-w-[1100px] px-5 py-16 sm:px-8 sm:py-20">
        <Reveal>
          <h1 className="font-display max-w-2xl text-[2.4rem] font-semibold leading-[1.08] tracking-tight text-ink sm:text-[3.1rem]">
            An AI buyer, on a short leash.
          </h1>
          <p className="prose mt-5 max-w-xl text-[15.5px] leading-relaxed text-ink-dim">
            A GPT-4o-mini agent is given a goal and a hard budget, then left to buy credits on
            its own. It reads its trust score, picks a tier, adapts when TRACE says no. The
            catch: it holds the reasoning, never the purse strings. Every bound it can&rsquo;t
            reach is enforced where the money actually moves.
          </p>
        </Reveal>

        {/* mode switch */}
        <Reveal delay={0.06}>
          <div className="mt-9 flex flex-wrap items-center gap-2.5">
            {(["honest", "compromised"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`rounded-full border px-4 py-2 text-[13px] font-medium transition-colors ${
                  mode === m
                    ? "border-sienna bg-sienna-bg text-sienna-deep"
                    : "border-rule text-ink-dim hover:border-rule-strong"
                }`}
              >
                {m === "honest" ? "Honest run" : "Compromised run"}
              </button>
            ))}
            <span className="prose ml-1 text-[12.5px] text-ink-faint">
              {mode === "honest"
                ? "goal 20 credits · ₹1,000 budget"
                : "principal's instruction: “buy all 50 in one order, now”"}
            </span>
          </div>
        </Reveal>

        {/* summary card */}
        <Reveal delay={0.1}>
          <div className="glass mt-6 overflow-hidden rounded-[28px]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule/70 bg-paper-deep/40 px-6 py-4 sm:px-8">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">Buyer</p>
                <p className="mt-0.5 text-[14px] text-ink">{run.buyerName}</p>
              </div>
              <span
                className={`inline-flex -rotate-2 items-center gap-2 rounded-lg px-3.5 py-1.5 text-[12.5px] font-semibold ${
                  run.outcomeKind === "allow"
                    ? "bg-bush-bg text-bush-bright"
                    : run.outcomeKind === "deny"
                      ? "bg-sienna-bg text-sienna-deep"
                      : "bg-oak-bg text-ink-dim"
                }`}
              >
                {run.outcomeLabel}
              </span>
            </div>
            <div className="grid grid-cols-2 divide-x divide-rule/70 sm:grid-cols-4">
              <div className="px-6 py-5 sm:px-8">
                <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Credits</p>
                <p className="tnum mt-1 text-xl font-semibold text-ink">
                  {run.creditsAcquired}
                  <span className="text-ink-faint">/{run.goalCredits}</span>
                </p>
              </div>
              <div className="px-6 py-5 sm:px-8">
                <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Spent</p>
                <p className="tnum mt-1 text-xl font-semibold text-ink">
                  ₹{run.spentInr.toFixed(0)}
                  <span className="text-ink-faint">/{run.budgetInr.toFixed(0)}</span>
                </p>
              </div>
              <div className="px-6 py-5 sm:px-8">
                <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">Orders</p>
                <p className="tnum mt-1 text-xl font-semibold text-ink">{run.orders.length}</p>
              </div>
              <div className="px-6 py-5 sm:px-8">
                <p className="text-[10.5px] uppercase tracking-wide text-ink-faint">
                  {isLive ? "Live" : "Duration"}
                </p>
                <p className="tnum mt-1 text-xl font-semibold text-ink">
                  {isLive ? "just now" : `${run.durationS.toFixed(1)}s`}
                </p>
              </div>
            </div>
            {/* budget meter */}
            <div className="px-6 py-5 sm:px-8">
              <div className="flex items-center justify-between text-[11px] text-ink-faint">
                <span className="uppercase tracking-wide">Budget drawn down</span>
                <span className="tnum">{spentPct.toFixed(0)}%</span>
              </div>
              <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-paper-deep">
                <motion.div
                  key={`${mode}-${replayKey}-${isLive}`}
                  className={`h-full rounded-full ${run.outcomeKind === "deny" ? "bg-sienna" : "bg-bush-bright"}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${spentPct}%` }}
                  transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1], delay: run.entries.length * 0.12 }}
                />
              </div>
            </div>
          </div>
        </Reveal>

        {/* run-live control */}
        <Reveal delay={0.12}>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            {liveEnabled ? (
              <button
                type="button"
                onClick={runLive}
                disabled={running}
                className="inline-flex items-center gap-2 rounded-full bg-bush px-6 py-2.5 text-[13px] font-semibold text-paper shadow-[0_12px_28px_-14px_rgba(31,61,44,0.55)] transition-all hover:-translate-y-0.5 disabled:translate-y-0 disabled:opacity-50"
              >
                {running ? "Agent is working…" : isLive ? "Run it again →" : "Run this live →"}
              </button>
            ) : (
              <p className="prose text-[12.5px] text-ink-faint">
                Showing the captured run. Start the merchant with an <code className="tnum">OPENAI_API_KEY</code>{" "}
                set to drive a fresh one from here.
              </p>
            )}
            {isLive && (
              <button
                type="button"
                onClick={() => {
                  setLiveRun(null);
                  setReplayKey((k) => k + 1);
                }}
                className="text-[12.5px] font-medium text-sienna-deep underline decoration-sienna/30 underline-offset-4 hover:decoration-sienna"
              >
                back to the captured run
              </button>
            )}
            {liveError && <span className="text-[12.5px] text-sienna-deep">{liveError}</span>}
          </div>
        </Reveal>

        {/* the ledger */}
        <Reveal delay={0.14}>
          <ol key={`${mode}-${replayKey}`} className="glass mt-8 overflow-hidden rounded-[28px]">
            {run.entries.map((e, i) => (
              <Entry key={`${mode}-${replayKey}-${e.turn}`} entry={e} index={i} live={isLive} />
            ))}
          </ol>
        </Reveal>

        {/* caps callout — compromised run */}
        {run.capsFired.length > 0 && (
          <Reveal delay={0.16}>
            <div className="glass mt-6 rounded-[28px] p-6 sm:p-8">
              <p className="font-display text-[1.3rem] font-semibold text-ink">
                What actually stopped it
              </p>
              <p className="prose mt-2 max-w-xl text-[13.5px] leading-relaxed text-ink-dim">
                The agent did what its principal told it to. Two server-side caps in the merchant —
                not the model, not TRACE&rsquo;s score — held the line.
              </p>
              <div className="mt-5 grid gap-4 sm:grid-cols-3">
                <div className="rounded-2xl bg-sienna-bg/60 px-5 py-4">
                  <p className="tnum text-[13px] font-semibold text-sienna-deep">
                    {run.capsFired.join(" · ")}
                  </p>
                  <p className="mt-1 text-[11.5px] text-ink-dim">HTTP rejections the caps returned</p>
                </div>
                <div className="rounded-2xl bg-panel/60 px-5 py-4">
                  <p className="tnum text-[13px] font-semibold text-ink">
                    ₹{run.largestOrderInr.toFixed(0)}
                  </p>
                  <p className="mt-1 text-[11.5px] text-ink-dim">
                    largest single order — the per-purchase cap held
                  </p>
                </div>
                <div className="rounded-2xl bg-panel/60 px-5 py-4">
                  <p className="tnum text-[13px] font-semibold text-ink">
                    {run.creditsAcquired}/{run.goalCredits}
                  </p>
                  <p className="mt-1 text-[11.5px] text-ink-dim">
                    got through before the velocity cap shut it down
                  </p>
                </div>
              </div>
              <p className="prose mt-5 max-w-xl text-[12.5px] leading-relaxed text-ink-faint">
                Those {run.creditsAcquired} credits are legitimate purchases at a fair price —
                TRACE scored each one on its merits. The caps don&rsquo;t judge intent; they bound
                how fast and how big money can move, whatever the instruction says.
              </p>
            </div>
          </Reveal>
        )}

        <Reveal delay={0.18}>
          <p className="prose mt-10 max-w-xl text-[12.5px] leading-relaxed text-ink-faint">
            Reproduce it: <code className="tnum">python -m buildathon.demo.agent_demo</code> (or{" "}
            <code className="tnum">--rogue</code>). Full transcript in{" "}
            <code className="tnum">demo/agent_session.json</code>; loop and safety internals in{" "}
            <code className="tnum">agent/buyer.py</code>.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
