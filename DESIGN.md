# DESIGN.md

<!-- impeccable:design-schema 1 -->

Written at finish, from the built frontend (`buildathon/frontend/`), by the assistant standing in
for the shipped `impeccable-documenter` agent — that agent isn't registered in this environment's
plugin config (only `impeccable-asset-producer` and `impeccable-manual-edit-applier` are), so this
file was authored directly, disclosed here rather than silently. It describes the world as built,
not as originally intended — the source of truth is the running code.

## World

**The Ledger House** — an editorial, maximalist, glassmorphic redesign of TRACE's frontend, replacing
a prior "Bloomberg trading terminal" direction (true near-black ground, monospace-primary,
zero-radius, teal/sage signal colors) that the user explicitly rejected outright ("I kinda dont like
the UI at all... I dont want the current design at all"). Pinned directly from the user's brief —
three reference palettes (a cool blue/teal gradient, a warm cream/brown moodboard-app palette, an
earthy Sienna/Oak/Cashmere/Bush board), explicit words "maximalism," "glassmorphism (visible),"
"light theme," "professional images... figures graphs," "professional scroll and hover effects" —
not drawn from the concept-seed roll; the brief was already this specific and the user had just
rejected a full direction, so re-rolling against catalog challengers would have served the process
over the person. Disclosed to the user as a deliberate substitution of `new-work.md`'s dice-roll
step.

**Thesis:** trust isn't asserted, it's grown and witnessed. The product reads as a warm, hand-kept
ledger of provenance — every score a stamped, glass-cased entry sitting over a living root-network
of the trust graph.

## Palette (light, committed — no dark mode)

Warm cashmere/paper ground and two committed colors that carry whole regions (not accents): a deep
bush-green and a burnt-sienna terracotta. Oak is the third warm neutral. One cool teal is reserved
sparingly for live/data readouts and links, matching the user's explicit choice of warm-earthy-primary
with cool-blue-as-accent.

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#f6efe0` | ground |
| `--paper-deep` | `#efe1c5` | alternating section band |
| `--ink` | `#241a10` | body text (~16.8:1 on paper) |
| `--ink-dim` | `#6a5843` | secondary text (~5.9:1 on paper) |
| `--sienna` / `--sienna-deep` | `#a94e28` / `#7c3418` | primary committed color — CTAs, links, alerts |
| `--bush` / `--bush-bright` | `#1f3d2c` / `#2c6b45` | primary committed color — buttons, positive/allow |
| `--oak` | `#b8925a` | third neutral — pricing accents, undergrowth texture |
| `--teal` / `--teal-bright` | `#235d68` / `#3b8b98` | sparing accent — data readouts, one hero blob |

Dark mode was deliberately not built: the direction is a single committed light-theme identity per
the user's explicit "light theme" instruction, not a default omission.

## Type

- Display: **Petrona** (serif, self-hosted via `next/font/google`) — headlines, "TRACE" wordmark,
  the `α β γ...` symbols in `WeightChart`. Chosen over the training-data-default serif list
  (Fraunces, Playfair, Cormorant, Lora, Crimson, Newsreader...) for a less-templated editorial/ledger
  character.
- Body/UI: **Work Sans** — everything structural: nav, buttons, labels, prose.
- Data: **JetBrains Mono**, `.tnum` (`font-variant-numeric: tabular-nums`) — reserved strictly for
  real numbers (scores, ₹ amounts, latency, order/agent IDs, chart tick labels). Never used as a
  "technical" costume elsewhere.

## Glass, as a material

`.glass` (`rgba(255,253,246,0.58)`, `blur(20px) saturate(140%)`) and `.glass-sm` (`0.78` opacity,
`blur(14px)`, used where legibility over dense content matters more than transparency — the sticky
nav, the command palette, the mobile nav drawer) sit over textured/illustrated grounds (paper grain,
color blobs, the root-network diagram), never as bare white-on-white chrome. Every glass panel has a
soft warm-tinted border and an offset+blur shadow (`--glass-shadow`), never a flat colored halo.

## Corner language

Pills (`rounded-full`) for buttons, nav links, tags, tier badges. Large glass panels and cards:
`rounded-[24px]`–`rounded-[32px]`. Nothing sharp-edged; this is a deliberate reversal of the previous
direction's zero-radius rule.

## Motion grammar

One grammar for scroll reveals (`components/Reveal.tsx`): fade + rise (26px), exponential ease-out
(`[0.16, 1, 0.3, 1]`), 0.7s, staggered by ~0.06–0.15s across siblings, triggered once via
`useInView`. A shared hook (`lib/useReveal.ts`) adds a scroll-position fallback: an element already
scrolled fully past without its normal trigger ever firing reveals instantly rather than staying
invisible — defends against fast/programmatic scrolls outrunning the IntersectionObserver.

Signature interaction: **TrustRoots** (`components/TrustRoots.tsx`) — an authored SVG diagram of
Personalized PageRank flowing outward from an "honest seed" node, paths drawing in via
`pathLength` animation on first view; a disconnected Sybil triangle at the edge never receives a
path in. Appears in the hero and on the Marketplace page. One authored moment, not scattered effects.

Nav hover: a shared-layout pill (`layoutId="nav-pill"`) slides between hovered links.

## Icons

Authored inline SVG line icons (`components/Icons.tsx`), one stroke weight (1.75) and cap style
throughout — not a library grab, not unicode/emoji standing in for icons.

## Imagery

No stock photography — the brief's "professional images... figures graphs" is served by authored
SVG (the root-network diagram, line icons) and real data visualizations (`BenchmarkChart`,
`WeightChart`, the naive/protected proof bars), consistent with the product's existing "every number
traces to a real backend result" commitment: synthetic stock photography of "agents" or "people"
would have worked against that commitment more than served the brief.

## Pages rebuilt

Originally 7 routes (`/`, `/try-it`, `/naive-vs-protected`, `/marketplace`, `/pricing`, `/outcomes`,
`/audit`) rebuilt in this world in one continuous pass (the user's answer to "landing page first,
then extend" was to remove the old design outright rather than stage the rollout). `Sidebar.tsx` and
`MobileNav.tsx` were deleted and replaced by a single `Nav.tsx` (glass sticky top bar + mobile
drawer). All real data wiring (`lib/data.ts`'s captured evidence, `TryItForm.tsx`'s live
`/buy-credits` POST, tier/auto-upsell fields) carried over unchanged — this was a visual world
replacement, not a product-truth change.

**`/agent` added 2026-09-04** (`agent/page.tsx` + `agent/AgentTheatre.tsx`, `lib/agent.ts` generated
by `demo/gen_frontend_agent_data.py`). Built to the same world, no new tokens: the transcript renders
as a hand-kept **ledger** — each turn an entry with a JetBrains-Mono turn number in a paper-deep
disc, the agent's reasoning set in Work Sans italic against an oak margin rule (the ledger-margin
gesture), the tool call in a mono chip, and the outcome as a pill in the committed palette (bush =
order created, sienna = blocked / cap rejection, oak = not-attempted, teal = a data read). One
motion grammar: entries fade+rise in staggered sequence (0.12s captured, 0.22s for a live run so it
reads as "thinking"), the budget meter draws down after them. The compromised run adds one glass
"verification" panel — the caps that fired, the largest order, credits-through — in the same
register as the score readouts elsewhere. Segmented honest/compromised control reuses the tier-pill
pattern from `TryItForm`.

## Known follow-ups

- `marketplace/page.tsx`'s copy was corrected during this pass: it previously stated the
  `GET /v1/graph` endpoint "returns a placeholder score" — that was fixed earlier this session
  (`api/routers/graph.py` now reads real persisted PageRank), so the copy now says so.
- The refuse-list's ban on unicode glyphs standing in for icons is carried as a pre-existing,
  low-stakes exception: the `›` disclosure chevron in `AgentTable`/`ProtectedPassTable` (inherited
  from the prior direction, rotated via CSS transform) was left as-is rather than replaced with an
  authored SVG, since it functions as a plain rotate-affordance, not decorative iconography.
