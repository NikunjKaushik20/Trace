# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Next.js (App Router) + TypeScript + Tailwind CSS + Framer Motion, scaffolded at `buildathon/frontend/`, standalone and self-contained (its own `package.json`, no dependency on anything outside `buildathon/`).

Revised from an earlier Vite decision: the user later added an explicit SEO requirement ("best professional SEO optimized website"), which a client-only Vite SPA cannot meet as well as a framework with real static generation and a metadata API — Next.js is the correct call once that requirement exists, not Vite. Recorded here so the reversal has a reason attached, not just a new answer.

## Users

Primary: the Razorpay AI Buildathon judging panel. Consumption is two-stage — first a 5-minute submission video (the only artifact the initial form actually asks for), then, if shortlisted, a technical panel that may browse the live site themselves and ask architecture questions. Secondary: the builder(s) themselves, using the site to rehearse and record that video.

## Product Purpose

TRACE Agentic Gateway: a graph-aware, Bayesian trust-scoring backend that gates autonomous AI-agent purchases from a merchant, submitted to Track 1 ("AI Growth & Agentic Commerce"). The frontend's job is to make the backend's real, already-verified behavior visible and interactive — not to simulate or mock capability the backend doesn't have.

## Positioning

Explicitly not an LLM-wrapper checkout demo. The scoring engine (Bayesian confidence bounds, CUSUM change-detection, Personalized PageRank, Sybil/clique penalties) is real, unit-tested, and built on an accepted CIKM 2026 paper. The submission's differentiator is verified rigor and honest self-reporting: a real production bug was found, root-caused, and fixed with a migration; a benchmark comparison against baselines is reported including a scenario where TRACE ties rather than wins; a scaled load test reports real numbers, not round ones. **This is a confirmed, binding brand commitment for the frontend, not just backend practice**: the UI must never display a number, claim, or state the backend cannot substantiate. Where the backend result is partial or unflattering (e.g. an order that was *created* but not yet *captured*; a benchmark tie), the UI shows that state honestly rather than smoothing it over.

The user was explicit: do not treat this as a hackathon-scrappy product. Treat it as a real product's flagship interface.

## Operating Context

Two real usage moments, not an internal daily-use dashboard: (1) screen-captured for a scripted 5-minute video, so the strongest three or four screens need to read instantly and look intentional in a recording; (2) live-browsed by a technical panel who may click into any of the seven pages and probe specific numbers. The UI should default to wiring against the real running backend (local TRACE + merchant instances, real Razorpay test-mode data) rather than static mock data, consistent with this project's established practice of verifying by running things, not asserting them.

## Capabilities and Constraints

Eight-page structure (page 8, the AI buyer agent, added 2026-09-04 — see below and NOTES.md #18):
1. Overview — problem, architecture, headline numbers.
2. Try It Live — interactive purchase trigger (`POST /buy-credits`) with full score breakdown, flags, and plain-language explanation shown inline.
3. The AI Buyer Agent — a gpt-4o-mini agent driving real `/buy-credits` calls to a goal within a hard budget; renders two captured runs (`demo/agent_session.json`, `agent_session_rogue.json`) as an animated ledger, honest and compromised, with a live "Run this" button (`POST /agent/run`, merchant-side, gated on `OPENAI_API_KEY`). The compromised run shows the server-side per-purchase and velocity caps rejecting an over-buy the model was told to make. This is the page that answers Track 1's "Build an agent" verb literally.
4. Naive vs. Protected — the before/after comparison table (`demo/audit_log.json`), the strongest single proof point.
5. Marketplace — trust graph + agent directory, two views of the same population (`GET /v1/graph`).
6. Growth & Pricing — `GET /catalog`'s trust-gated tiers and per-agent tier-progress hints.
7. Measured Outcomes — benchmark-vs-baselines chart and scaled-load-test stats, both from real captured JSON reports.
8. Audit & Governance — full filterable audit log, system health, review queue, policy list (note: policies are recorded but not yet wired into live scoring — label as a log, not a live control), and the `anchor_commitment`/`refresh_hint` data labeled accurately (an audit hash, not a blockchain proof).

Constraint: every screen must be able to point at a real backend response it is rendering. No invented sample transactions, no placeholder "Lorem ipsum" agents.

## Evidence on Hand

Real, already-captured results from this session, safe to use verbatim in the UI:
- Naive/protected demo: 9/9 vs 3/9 orders created; Rs 600 → Rs 0 fraud exposure prevented; real Razorpay test-mode order IDs.
- Scaled load test (`demo/scaled_load_test_report.json`): 36 agents, 0 of 20 honest agents wrongly blocked, 16 of 16 fraud agents caught, latency p50=209.6ms / p95=292.0ms / p99=616.2ms.
- Benchmark vs. baselines (`demo/benchmark_report.json`): collusion_ring 5%/32%, sybil_cluster 53%/74%, strategic_default 0%/0% (an honest tie, not omitted), game_theoretic 14%/69%.
- A real, fixed production bug (CUSUM persistence) with before/after evidence, and a real, fixed production migration-history divergence — both are pitch material, not implementation detail, if the panel round goes technical.

## Product Principles

1. Every number on screen traces to a real, already-run backend result — the UI does not get to be more optimistic than the data.
2. Explainability is structural, not an afterthought: score component breakdowns and flag meanings are always visible next to a decision, never hidden behind an extra click.
3. Honesty about limitations is a design feature: ties, un-captured payment states, and stubbed data get shown as themselves, never smoothed into looking better than they are.
4. The naive-vs-protected contrast is the product's central idea and must never be visually subordinate to any other screen.
5. Rich and considered, not templated: a wide palette and visible glassmorphism are the deliberately chosen register (revised from an earlier "confident and restrained" rule — a first, since-replaced version of this site made a different mistake, four palette steps used as four literal full-bleed page bands, and the user rejected it explicitly as unprofessional; that specific device, a page literally re-skinned per section, stays refused). The current direction (see `DESIGN.md`) commits two colors to whole regions consistently across every page rather than swapping palette per section, and reserves glass specifically for "verification" surfaces (score readouts, the nav, proof panels) rather than as generic card chrome — richness comes from real data density, texture, and motion, not from randomizing the palette screen to screen.
6. Say less. Real numbers and a confident layout carry the pitch — the copy does not need to explain what the visual hierarchy already shows.

## Brand Commitments

**Binding, stated explicitly after a correction**: this product's UI never names the buildathon, the track, or the competition anywhere in the shipped surface — no "Track 1," no "Razorpay AI Buildathon," no submission-labeling of any kind on the actual pages. TRACE is presented as a real product on its own terms. Competition/track context belongs in the pitch video and any written submission material, never in the product UI itself. A first version of this site violated this by putting "Track 1 — AI Growth & Agentic Commerce · Razorpay AI Buildathon" in the hero; that mistake is the reason this rule is written down instead of assumed.
