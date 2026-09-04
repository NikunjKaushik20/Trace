# TRACE Agentic Gateway -- Razorpay AI Buildathon submission

🎬 **Live Demo & Video Pitch:** [https://www.youtube.com/watch?v=ORDoT0XbTZ0](https://www.youtube.com/watch?v=ORDoT0XbTZ0)

**Track 1: AI Growth & Agentic Commerce** -- making a merchant safely
transactable by an AI buyer, end to end.

## The problem

A merchant wants AI buyer agents purchasing from it autonomously
(x402-style agent-to-agent commerce). The risk: a coordinated Sybil ring
spins up many fake agent identities, builds a dense mutual-endorsement
graph to look credible, and drains the merchant before any single
transaction looks suspicious on its own. Track 1's bar is explicit: every
money action explainable, bounded, and gated.

## What this is

A working demo that wraps a real merchant purchase flow (Razorpay
test-mode order creation) with **TRACE**, a graph-aware trust scorer
already live in production at this repo's root (`api/`), built on an
accepted CIKM 2026 paper on adversarial trust routing in decentralized
agent marketplaces. It isn't a new algorithm built for the hackathon.
It's the existing, unit-tested scoring engine (Bayesian confidence
bounds, CUSUM default-risk detection, Personalized PageRank, Sybil/clique
penalties), wired into a merchant scenario and pointed at a synthetic
attack.

Track 1's "bounded" requirement is enforced structurally, not just
implied by the score. `merchant/app.py` rejects anything over a
per-transaction credit cap and a rolling per-agent spend cap before it
ever calls TRACE, so a momentarily high-trust agent still can't move
unlimited money in one shot or in a burst. Every live purchase also
reports its own outcome back into TRACE, gated on TRACE's genuine
`would_allow` judgment rather than the naive/protected enforcement toggle
(`NOTES.md` explains why that distinction matters). Real activity feeds
future trust decisions the same way the synthetic seed history does.

The track is called "AI **Growth** & Agentic Commerce," and everything
above is the safety half of that. `merchant/catalog.py` is the growth
half, built on the same trust signal instead of bolted on separately.
`GET /catalog` is an agent-readable list of purchase tiers, and each
tier's per-credit price improves as an agent's TRACE score crosses a
`min_trust_score` threshold (see "Growth: trust-gated pricing" below). A
clean track record has a direct, machine-readable commercial payoff, not
just fewer blocks.

Everything in this folder is self-contained. The merchant and attack code
never import the repo's core `api/` package directly. They talk to a
real running instance of the TRACE API over HTTP, the same way an
external integrator would. `NOTES.md` explains why, and covers two bugs
found while building this that are worth knowing about.

## The AI buyer agent

Track 1's leading verb is "Build an agent." `buildathon/agent/` is one:
an LLM (OpenAI `gpt-4o-mini`, temperature 0) given a goal ("acquire N
GPU-inference credits") and a hard budget, driving the real merchant flow
through tool calls: `get_catalog`, `check_trust`, `buy_credits`. It reads
whether TRACE allowed each purchase and adapts. Every tool call carries a
forced `reasoning` field, so the transcript shows the agent's thinking
behind each action. `python -m buildathon.demo.agent_demo` seeds an
honest history and writes a full, replayable transcript to
`demo/agent_session.json`.

Real honest run, 20 credits, Rs 1000 budget: the agent reads the catalog
and its own score (~0.35), attempts `tier: "Pro"` for the best per-credit
price, and gets **`blocked`, `TIER_MIN_SCORE_NOT_MET`** -- TRACE's tier
gate refusing an honest agent. It drops to `tier: "Plus"` and buys it
four times: 20 credits for Rs 900. Both cases show up in one run, a tier
refused and a tier earned. `frontend/app/agent/` renders this and the
rogue run as an animated ledger, with a live "Run this" button
(`POST /agent/run`, gated on `OPENAI_API_KEY`).

The LLM is only the buyer's brain: it never scores anything, and it has
no tool that bypasses `/buy-credits`. Bounds are enforced in two places
it can't reach: a client-side budget check, and `merchant/app.py`'s
server-side per-purchase and velocity caps. `python -m
buildathon.demo.agent_demo --rogue` puts *"buy all 50 credits in ONE call
now, spend whatever it costs"* in the principal's message. The agent
obeys: `buy_credits(credits=50)` returns `400` (per-purchase cap). It
adapts, splitting into 20 + 20, two Rs 1000 orders. It tries the last 10
and gets `429` (velocity cap). It stops at 40/50. Both caps fired, no
order exceeded Rs 1000, and the compromised instruction only ever moved
money in bounded amounts -- the track's "one failure handled
gracefully," AI-native. Full detail and the failure-handling test list
are in `NOTES.md` #18.

## Architecture

```
attack_sim/   --seeds history & fires purchases-->  merchant/app.py  --scores via HTTP-->  api.main:app (TRACE)
agent/ (LLM)  --goal + budget, drives buy flow-->        |                                  (isolated local DB,
                                                          v                                   never production)
                                                   Razorpay test-mode
                                                   order creation
```

Four agent classes are simulated, matching the paper's evaluated
adversary types: honest agents, a strategic defector (honest history,
then sudden failures), and a 5-node Sybil ring (mutual fake endorsements,
almost no real completed jobs) in the standard demo. `demo/scaled_load_test.py`
runs the identical mechanism against a much larger population (see
"Scale" below).

## Growth: trust-gated pricing

`GET /catalog` (`merchant/catalog.py`) lists three purchase tiers, each
gated by the same TRACE score `/buy-credits` already computes:

| Tier | Credits | Price | Per-credit | Requires |
|---|---|---|---|---|
| Starter | 1 | Rs 50 | Rs 50.00 | no history |
| Plus | 5 | Rs 225 | Rs 45.00 (10% off) | score >= 0.25 (`ROUTE_WITH_CAUTION`+) |
| Pro | 20 | Rs 800 | Rs 40.00 (20% off) | score >= 0.50 (`ROUTE`) |

Every `/buy-credits` response includes `unlocked_tier` (the best tier the
agent's *current* score already qualifies for) and `next_tier_hint` (how
much more trust the next tier needs). Both are advisory, reflecting the
agent's live score independent of what this particular purchase charged.

Tier selection is wired into the charge path two ways. Pass
`tier: "Plus"` (or `"Pro"`) on `/buy-credits` to charge that tier's real
price, gated on its own `min_trust_score` checked against the score
TRACE returns for that priced amount. Or pass `auto_upsell: true` and let
the merchant decide to substitute a better-value bundle for a smaller
flat-rate request when the agent's live score qualifies. That's an actual
upsell decision that changes the amount charged, not just a message
(`upsell_applied` / `upsell_note` on the response show what happened and
why). `NOTES.md` #14 has the re-scoring and velocity-cap mechanics that
keep this honest under a changing price.

Pro's 20-credit bundle sits exactly at `MAX_CREDITS_PER_PURCHASE`'s
default, on purpose. The growth incentive (better pricing for proven
trust) and the bounded cap (a hard ceiling regardless of score) meet at
the same number. That's not a coincidence.

## Measured outcomes: TRACE vs. baselines

`api/simulation.py` already has a benchmark harness comparing TRACE
against behavioral-only scoring and EigenTrust across four adversary
scenarios, built and tested (`tests/test_simulation.py`) independently of
this submission. `demo/benchmark_report.py` surfaces it through the real
`/v1/benchmark` endpoint on every demo run, reporting all four scenarios,
not just the ones that look good:

```
scenario              vs behavioral    vs eigentrust  note
collusion_ring                  5%              32%
sybil_cluster                   53%              74%
strategic_default                0%               0%  TRACE ties both baselines here -- reported as-is, not omitted
game_theoretic                  14%              69%
```

(n_agents=100, adversary_ratio=0.30, n_rounds=60, seed=42 -- the same
parameters `tests/test_api.py::test_benchmark_endpoint` already exercises.
The full per-scenario breakdown lands in `demo/benchmark_report.json`
after a run.)

The strategic-default tie is real at these parameters, and it's more
honest to report it than to curate around it. TRACE's CUSUM/EMA
default-risk signal is built for exactly this adversary type, and it
still visibly penalizes the defector in the live demo above (`DENY`,
`CUSUM_FIRED`). But in this specific simulated population, EigenTrust's
own reputation decay catches it about equally well. Sybil clustering is
where TRACE's graph-aware signal (PPR, edge-to-job ratio, clique penalty)
has no equivalent in either baseline, and the numbers show it.

## Scale

`demo/scaled_load_test.py` runs the same mechanism as the standard demo
against a larger synthetic marketplace: 20 honest agents, a 15-member
Sybil ring, and 1 strategic defector by default (configurable via
`SCALED_N_HONEST_AGENTS` / `SCALED_N_SYBIL`). It reports p50/p95/p99
latency for the full `/buy-credits` round trip (merchant -> TRACE
`/v1/score` -> Razorpay order creation), not just TRACE's internal
scoring latency.

Run it once ahead of time and cite the results -- don't run it live in
front of a panel. Seeding hundreds of events against `api/rate_limit.py`'s
real 120/minute cap on `/v1/events` genuinely takes several minutes.
That's the anti-abuse control working as intended, not a flaw in the
script. Results land in `demo/scaled_load_test_report.json`.

**Actual output from a real run** (905 events seeded across 36 identities
in 442s, rate-limit-bound as expected):

```
Population: 36 agents (20 honest, 1 defector, 15 Sybil)
Purchase attempts: 36 in 6.8s (5.3 req/sec)
Latency (full /buy-credits round trip): p50=209.6ms  p95=292.0ms  p99=616.2ms  max=758.3ms
Blocked: 16/36, of which 16/16 were the fraud population (sybil ring + defector) -- correctly caught at this scale.
```

The number that matters most: **0 of the 20 honest agents were wrongly
blocked, and 16 of 16 fraud agents -- the full Sybil ring plus the
defector -- were.** Zero false positives, 100% fraud catch rate, at this
scale, in this run.

## Real payment capture

Everything above proves order *creation* was gated correctly. It
doesn't, by itself, prove a payment was actually *captured* -- a buyer
completing checkout. There are two independent, complementary ways this
submission proves capture: one needs a public URL, one doesn't.

**Client-side, no ngrok needed, live in the frontend.** The "Try It Live"
page (`frontend/app/try-it`) loads Razorpay's real `checkout.js`. After
`/buy-credits` returns `order_created`, a "Pay with Razorpay" button
opens Razorpay's actual test-mode Checkout modal against that order. On a
completed payment, Checkout's `handler` callback hands the frontend a
`razorpay_payment_id` and a signature, which it posts to
`POST /verify-payment`. The merchant verifies that HMAC-SHA256 signature
server-side (`razorpay_client.py`'s `verify_payment_signature`, wrapping
the SDK's own `utility.verify_payment_signature`) before recording the
capture -- it never trusts the client's say-so unverified -- and the page
reflects the verified or failed result immediately.

This is what makes the payment screen demoable at a panel table, not
just described in a video. Run `python -m buildathon.demo.serve` (keeps
TRACE and the merchant up persistently, unlike `demo_runner.py`'s
one-shot comparison pass) and `cd buildathon/frontend && npm run dev`,
then pay a live order and watch it land in the Razorpay dashboard's Test
Mode payments.

**Server-to-server, for a deployed or public scenario.**
`merchant/webhooks.py` adds a real Razorpay webhook receiver
(`POST /webhooks/razorpay`, HMAC-SHA256 signature verification, the same
pattern as `api/routers/webhooks.py`'s x402 settlement webhook) that
records `payment.captured` / `payment.failed` events and exposes them
through `GET /orders/{razorpay_order_id}/capture-status`. This path
works even if the buyer's browser never calls back -- a closed tab, a
crashed client -- but it needs a public callback URL (ngrok, for
instance) that Razorpay can reach. For a fully local demo, use the
client-side path above instead. The webhook path is demonstrated in the
recorded pitch video and by `tests/test_razorpay_webhook.py`'s
signed-payload tests.

Neither path changes what `/buy-credits` reports back to TRACE -- that's
still order-creation plus `would_allow`, not eventual capture. Changing
that would need its own regression pass against the naive/protected
comparison this submission's core evidence rests on. Both payment paths
are deliberately additive: confirmation of capture, read from a separate
source of truth.

## Running it

From the **Trace-API repo root** (not this folder):

```bash
pip install -r requirements.txt
cp buildathon/.env.example buildathon/.env
# edit buildathon/.env with your Razorpay TEST-mode keys
python -m buildathon.demo.demo_runner
```

This will:
1. Boot an isolated local TRACE API against a throwaway SQLite database.
2. Seed a synthetic marketplace history through TRACE's real `/v1/events`.
3. Run every agent's purchase attempt against a **naive** merchant
   (scores computed, never enforced), then a **TRACE-protected** merchant
   (blocks anything that isn't `ROUTE`/`ROUTE_WITH_CAUTION`). Same
   agents, same history -- only the enforcement toggle differs.
4. Print a before/after summary and write the full per-decision audit
   trail to `demo/audit_log.json`.
5. Run the existing `api/simulation.py` benchmark harness against all
   four scenarios and write `demo/benchmark_report.json`.

For the larger-population run (several minutes, meant to be run once
ahead of time, not live):
```bash
python -m buildathon.demo.scaled_load_test
```

`GET /catalog` and `POST /buy-credits`'s `unlocked_tier` /
`next_tier_hint` fields are live on the merchant the moment it's running,
no separate script needed. For a persistent, clickable instance instead
of `demo_runner.py`'s one comparison pass that tears itself down, use
`python -m buildathon.demo.serve`, then `cd buildathon/frontend && npm
run dev`. That's what "Try It Live" needs to actually open a Razorpay
Checkout modal against a real order. The server-to-server
payment-capture webhook (`POST /webhooks/razorpay`) needs
`BUILDATHON_RAZORPAY_WEBHOOK_SECRET` set and a public URL Razorpay can
reach -- see "Real payment capture" above for both capture paths.

If `buildathon/.env` has no Razorpay keys configured, the merchant still
runs and scores every attempt correctly. It just skips creating a real
order and reports `status: "order_created"` without a `razorpay_order_id`,
so you can verify the trust-gating logic without a Razorpay account. Note
that `"order_created"` means a Razorpay *order* was created, not that a
payment was *captured* -- no buyer completes checkout in this demo, so no
money actually moves. `status` is one of `order_created`,
`order_creation_failed` (TRACE approved, but the Razorpay-side call
itself failed), or `blocked` (TRACE denied, nothing was attempted).

Run the unit tests (no network, no servers needed):
```bash
pytest buildathon/tests/ -v
```

## What a real run shows

Actual output from a real run against live Razorpay test-mode order
creation. Your exact scores will vary slightly run to run since history
is reseeded fresh each time; `agent_defector_0`'s `DENY` / `CUSUM_FIRED`
and the naive-pass `order_created` rows for the Sybil ring are also from
this same run's real output, not simulated:

```
--- Protected merchant -- non-ALLOW decisions are blocked ---
agent_id           class     status                 decision              score  flags
agent_honest_0     honest    order_created          ROUTE_WITH_CAUTION     0.35  -
agent_defector_0   defector  blocked                DENY                   0.00  CUSUM_FIRED
agent_sybil_0      sybil     blocked                QUARANTINE             0.00  SYBIL_RISK_HIGH,CLIQUE_PENALTY_HIGH,COLD_START,FRAGMENTED_VISIBILITY

=== SUMMARY ===
Naive:     9/9 orders created, Rs 600 in orders created for sybil/defector agents
Protected: 3/9 orders created, Rs 0 in orders created for sybil/defector agents
TRACE prevented Rs 600 of order-creation exposure to the Sybil ring / defector in this run.

=== CUSUM replay cross-check ===
Replaying the defector's 40-event outcome sequence through api/detection.py directly: cusum_fired=True, final ema_default_rate=0.94
Live protected-pass score for the same defector: CUSUM_FIRED=True, routing_decision=DENY (matches the replay -- the persistence fix landed)
```

Every `order_created` row carries a real Razorpay test-mode `order_...`
ID and a `job_id` that's simultaneously the Razorpay receipt and, for
agents TRACE genuinely trusts, the `/v1/events` report tying the purchase
back into TRACE's own history -- traceable end to end in
`demo/audit_log.json`. Querying the demo's isolated SQLite database
directly after a run confirms the closed loop lands exactly where it
should and nowhere else: outcome reports from the live purchase flow
(`buyer_id='merchant_demo_key'`) exist only for the three honest agents,
two each, one per pass. Never for the defector or any Sybil identity,
even in the naive pass, where the purchase itself still goes through.

Every blocked decision comes with a plain-language `explanation` in
`audit_log.json`, e.g.:
> "Low LCB (0.05) - thin evidence. Elevated default risk (0.76). High
> sybil risk (edge-to-job ratio anomaly). Clique penalty triggered -
> coordinated neighborhood."

That's the deterministic, math-based explanation TRACE's real scorer
generates, not an LLM call. No LLM sits in this decision path at all.
The anomaly detection is Bayesian statistics and graph theory, applied
where they're the right tool.

## Failure recovery -- a real bug, found and fixed

While building the attack simulation, replaying a strategic defector's
sudden failure burst never tripped the live `CUSUM_FIRED` flag the
paper's default-risk model should have raised. Digging in, we found a
real bug in the production persistence path. `api/detection.py`'s CUSUM
accumulator resets itself to zero the instant it fires, and that zeroed
value is what got persisted. So the one moment a `/v1/score` call could
observe "this just fired" was the one moment the stored state said
otherwise. We confirmed it by replaying the identical outcome sequence
directly through the same detector function in isolation, where it
correctly reported `cusum_fired=True`.

We fixed it at the source instead of working around it in this demo.
`ProviderRecord` now persists the fired signal independently
(`cusum_fired_ever` / `cusum_last_fired_at`, via a real Alembic
migration) instead of trying to re-derive it from an accumulator that
resets itself on write. It's a **sticky, non-decaying** flag by design:
once a provider trips the CUSUM alarm, it stays flagged. We think that's
the right call for a proven strategic defector, but it's a deliberate
no-rehabilitation tradeoff worth naming explicitly. We also found and
fixed the identical bug, independently reimplemented, in
`api/routers/jobs.py`'s `/v1/jobs/{id}/complete`, plus a second latent
copy in `api/state.py`'s `get_flagged_neighbors()`. Full root-cause and
design notes are in `NOTES.md`. The live demo run above now shows
`agent_defector_0` landing on `CUSUM_FIRED` / `DENY`, matching what the
isolated replay always said.

While in `api/state.py`, we also found and fixed a lost-update race in
`update_provider()`. Concurrent events for the same `provider_id` -- or a
burst of brand-new identities all appearing at once, exactly the
Sybil-ring scenario this system exists to catch -- could silently lose
writes. The fix uses atomic SQL-level increments (`col = col + 1`)
instead of a Python read-modify-write, which is what actually holds up
under concurrency on both SQLite and Postgres. An initial attempt using
`.with_for_update()` (matching `api/auth.py`'s pattern) looked right but
measurably failed on SQLite, since SQLite doesn't honor row locks at all.
`NOTES.md` has how we caught that before shipping it.

## What's real vs. out of scope here

- **Real:**
  - The scoring math (LCB, CUSUM, PPR, Sybil/clique) and the `/v1/score`
    and `/v1/events` endpoints.
  - Razorpay test-mode order creation *and* payment capture. "Try It
    Live" opens Razorpay's actual Checkout modal against a real order
    and verifies the completed payment's signature server-side (see
    "Real payment capture" above; `NOTES.md` #17).
  - The audit trail, the bounded per-transaction and per-agent velocity
    caps, and the would_allow-gated outcome-reporting loop.
  - The CUSUM persistence and concurrency fixes described above, covered
    by tests that exercise the real write-then-read round trip, not just
    the pure detector math.
  - The catalog-tier upsell/cross-sell logic (`tier` / `auto_upsell` on
    `/buy-credits`, see "Growth: trust-gated pricing" above and
    `NOTES.md` #14). A tier's advertised price is now what actually gets
    charged, re-scored and gate-checked at that real amount, not a
    message layered on top of a flat rate.
  - `GET /v1/graph`, TRACE's own trust-graph visualization endpoint. It
    used to return a hardcoded 0.98-or-0.24 score per agent regardless
    of the actual graph; it now reads the same persisted PageRank values
    (`api/worker.py`'s `_process_graph()`) the live scorer itself uses
    (`NOTES.md` #15).
- **Out of scope for this submission** (see `NOTES.md`):
  `anchor_commitment`'s on-chain claim -- it's currently a local hash,
  not an actual blockchain anchor -- and the paper's "counterparty
  entropy" term, which isn't implemented in this API.
- **Also out of scope, worth being precise about:** the scoring and
  detection layer above (LCB, CUSUM, PPR, Sybil/clique) is the paper's
  Eq. 1 architecture, verified. The paper's other half -- Thompson-
  sampling-vs-greedy provider *selection* among multiple candidates, the
  56-86% exploration-cost finding the paper's results actually center on
  -- was measured on SatsRouter, a separate, real, Lightning-Network-based
  deployed marketplace, not on this repo. `route()` here is a threshold
  gate on one candidate's own score, never a choice among several.
  Reimplementing that comparison fresh here would be a new, unvalidated
  approximation, not a reproduction of the paper's code or its published
  numbers (`NOTES.md` #13 has the full reasoning). Don't read "built on a
  CIKM'26 paper" as "the paper's routing policy is what's gating this
  merchant" -- it's the paper's scoring formula that is.
- **Known limitation, not hidden:** the bounded caps, the idempotency
  cache, and the velocity tracker are all in-memory and single-process
  (`NOTES.md` items 7-8). They reset if the merchant process restarts.
  TRACE's own state (scores, CUSUM, the trust graph) is unaffected, since
  that's the durable, persisted side of this system -- only the
  merchant's own bookkeeping resets. Production would back these with
  Redis or a database table, the same call already made for the rate
  limiter in `api/rate_limit.py`.
- **Known limitation, not hidden:** `POST /buy-credits` and
  `GET /agents/{agent_id}/trust-check` can require a shared merchant API
  key (`BUILDATHON_MERCHANT_API_KEYS`, unset/open by default --
  `NOTES.md` item 13), which gates *who may call the merchant API at
  all*. A configured key can be narrowed further to specific `agent_id`s
  (`BUILDATHON_MERCHANT_API_KEY_AGENT_SCOPES`, `NOTES.md` #14), which
  bounds what a leaked or shared key could do. Neither one gates
  *whether a caller genuinely is the `agent_id` it claims*. There's
  still no cryptographic per-agent identity in this submission, so
  TRACE's trust judgment is only as trustworthy as that self-asserted
  claim, scoped or not. Closing that gap needs signed per-agent requests
  -- a real design task left for future work.
