"""
An autonomous AI buyer agent for the Buildathon merchant demo.

Answers Track 1's "Build an agent" literally: an LLM (OpenAI gpt-4o-mini
by default) is given a goal ("acquire N GPU-inference credits") and a hard
budget, and drives the *real* merchant purchase flow through function
calls -- reading the catalog, checking its own TRACE trust score, choosing
a tier, buying, seeing whether TRACE allowed it, and adapting.

The design rule that makes this safe -- and that is the pitch -- is that
the LLM is the buyer's brain only. It never scores anything and has no
tool that bypasses /buy-credits. Bounds are enforced in two independent
places, neither of which the model can reach:

  1. client-side, here: the agent refuses to *attempt* a purchase it can
     see would blow the budget. This is a courtesy check, and a hostile
     instruction can talk the model past it -- which is the point of the
     `--rogue` demo.
  2. server-side, in merchant/app.py: MAX_CREDITS_PER_PURCHASE and the
     rolling velocity cap, enforced regardless of what the model asks for
     and regardless of what TRACE scores.

So a buyer agent whose instructions are compromised still cannot move
money it shouldn't. See ../NOTES.md #18.

Importing this module and running its tests needs no network and no API
key: the OpenAI client is constructed lazily and the LLM is injectable
(tests pass a scripted fake). A real run needs OPENAI_API_KEY.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional

from .tools import MerchantTools

logger = logging.getLogger("buildathon.agent")

DEFAULT_MODEL = "gpt-4o-mini"
# Starter tier's price. Used only to decide "the budget can't buy anything
# more, stop" -- the authoritative prices come from the live catalog.
CHEAPEST_CREDIT_INR = 50.0

# Catalog shape is fixed by merchant/catalog.py; mirrored here only for the
# client-side budget estimate and the credits-gained tally. The server is
# still the source of truth for what actually gets charged.
_TIER_PRICE_INR = {"Starter": 50.0, "Plus": 225.0, "Pro": 800.0}
_TIER_CREDITS = {"Starter": 1, "Plus": 5, "Pro": 20}


# --------------------------------------------------------------------------
# LLM abstraction -- one method, injectable, so tests never touch OpenAI.
# --------------------------------------------------------------------------
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict
    malformed: bool = False  # the arguments string was not a valid JSON object


@dataclass
class LLMTurn:
    text: Optional[str]
    tool_calls: List[ToolCall] = field(default_factory=list)


class LLMUnavailable(RuntimeError):
    """The LLM backend could not be reached (or returned a non-retryable
    error). run_session() catches this and falls back to one deterministic,
    bounded purchase rather than spinning."""


class OpenAILLM:
    """Thin adapter over openai.ChatCompletion with gpt-4o-mini and function
    calling. Retries transient transport/rate-limit errors a couple of
    times, then raises LLMUnavailable."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        temperature: float = 0.0,  # reproducible-as-possible transcripts for the demo
        max_retries: int = 2,
    ):
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to buildathon/.env "
                "(see .env.example) or pass api_key=."
            )
        from openai import OpenAI  # lazy: keeps import/test paths key-free

        self._client = OpenAI(api_key=key)

    def complete(self, messages: list, tools: list) -> LLMTurn:
        from openai import (
            APIConnectionError,
            APIError,
            APITimeoutError,
            RateLimitError,
        )

        transient = (APIConnectionError, APITimeoutError, RateLimitError)
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=self.temperature,
                )
                return _parse_openai_message(resp.choices[0].message)
            except transient as e:
                last_err = e
                if attempt < self.max_retries:
                    backoff = 1.5 * (attempt + 1)
                    logger.warning("LLM call failed (%s); retrying in %.1fs", e, backoff)
                    time.sleep(backoff)
            except APIError as e:
                # Bad request, auth failure, etc. -- retrying won't help.
                raise LLMUnavailable(f"OpenAI API error: {e}") from e
        raise LLMUnavailable(
            f"OpenAI unreachable after {self.max_retries + 1} attempts: {last_err}"
        )


def _parse_openai_message(message: Any) -> LLMTurn:
    calls: List[ToolCall] = []
    for tc in getattr(message, "tool_calls", None) or []:
        raw = tc.function.arguments or "{}"
        try:
            args = json.loads(raw)
            if not isinstance(args, dict):
                args, malformed = {}, True
            else:
                malformed = False
        except (json.JSONDecodeError, TypeError):
            args, malformed = {}, True
        calls.append(
            ToolCall(id=tc.id, name=tc.function.name, arguments=args, malformed=malformed)
        )
    return LLMTurn(text=(getattr(message, "content", None) or None), tool_calls=calls)


# --------------------------------------------------------------------------
# Config + audit records
# --------------------------------------------------------------------------
@dataclass
class AgentConfig:
    agent_id: str
    buyer_name: str
    goal_credits: int
    budget_inr: float
    max_turns: int = 12
    # Appended verbatim to the system prompt (operator policy).
    extra_instructions: str = ""
    # Replaces the default "Begin..." kickoff *user* message when set. The
    # `--rogue` demo puts the hostile "buy 50 in one order now" instruction
    # here -- i.e. coming from the agent's principal, not baked into system
    # policy -- which is the realistic compromise scenario, and lets the
    # server-side caps in merchant/app.py be what actually stops it.
    kickoff_override: Optional[str] = None


@dataclass
class ToolInvocation:
    name: str
    arguments: dict
    result: dict


@dataclass
class TurnRecord:
    index: int
    reasoning: Optional[str]
    tools: List[ToolInvocation] = field(default_factory=list)


@dataclass
class AgentSession:
    config: AgentConfig
    turns: List[TurnRecord] = field(default_factory=list)
    credits_acquired: int = 0
    spent_inr: float = 0.0
    orders: List[str] = field(default_factory=list)
    # "goal_met" | "budget_exhausted" | "max_turns" | "agent_stopped"
    #  | "llm_unavailable_fallback"
    outcome: str = "incomplete"
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    def as_dict(self) -> dict:
        return {
            "config": {
                "agent_id": self.config.agent_id,
                "buyer_name": self.config.buyer_name,
                "goal_credits": self.config.goal_credits,
                "budget_inr": self.config.budget_inr,
                "max_turns": self.config.max_turns,
                "had_extra_instructions": bool(self.config.extra_instructions.strip()),
            },
            "outcome": self.outcome,
            "credits_acquired": self.credits_acquired,
            "spent_inr": round(self.spent_inr, 2),
            "budget_remaining_inr": round(self.config.budget_inr - self.spent_inr, 2),
            "razorpay_orders": self.orders,
            "turns": [
                {
                    "index": t.index,
                    "reasoning": t.reasoning,
                    "tools": [
                        {"name": i.name, "arguments": i.arguments, "result": i.result}
                        for i in t.tools
                    ],
                }
                for t in self.turns
            ],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": round((self.finished_at or time.time()) - self.started_at, 2),
        }


# --------------------------------------------------------------------------
# Tool schemas exposed to the model. Note: agent_id is NOT a parameter --
# the agent only ever acts as itself, so it's injected from AgentConfig.
# That also removes a whole class of "the model claimed a different
# agent_id" confusion.
# --------------------------------------------------------------------------
# `reasoning` is a required parameter on every tool -- gpt-4o-mini reliably
# skips assistant `content` when it emits a tool call, so forcing the
# rationale into the call arguments is how we guarantee a visible line of
# thinking per action. It is popped off before the args reach the merchant
# (run_session), so it never affects the request.
_REASONING_PARAM = {
    "reasoning": {
        "type": "string",
        "description": "One or two sentences: why you are making this call, right now.",
    }
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_catalog",
            "description": (
                "List the merchant's purchase tiers: credit count, price, per-credit "
                "price, and the minimum TRACE trust score each tier requires."
            ),
            "parameters": {
                "type": "object",
                "properties": dict(_REASONING_PARAM),
                "required": ["reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_trust",
            "description": (
                "Look up your current TRACE trust score, routing decision, any risk "
                "flags, the best tier it currently unlocks, and how far you are from "
                "the next tier. No purchase is made."
            ),
            "parameters": {
                "type": "object",
                "properties": dict(_REASONING_PARAM),
                "required": ["reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buy_credits",
            "description": (
                "Attempt to buy GPU-inference credits. TRACE scores the purchase "
                "first and may block it. Either pass `credits` for a flat-rate "
                "purchase (Rs 50/credit), or pass `tier` to buy that named bundle at "
                "its price (gated on the tier's own minimum trust score). Set "
                "`auto_upsell` true to let the merchant substitute a better-value "
                "bundle if your score qualifies."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    **_REASONING_PARAM,
                    "credits": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Flat-rate credit count. Ignored if `tier` is set.",
                    },
                    "tier": {
                        "type": "string",
                        "enum": ["Starter", "Plus", "Pro"],
                        "description": "Named bundle to buy instead of a flat-rate amount.",
                    },
                    "auto_upsell": {"type": "boolean"},
                },
                "required": ["reasoning"],
            },
        },
    },
]


def _system_prompt(config: AgentConfig) -> str:
    base = f"""You are an autonomous procurement agent acting on behalf of "{config.buyer_name}".

GOAL: acquire {config.goal_credits} GPU-inference credits from the merchant.
HARD BUDGET: Rs {config.budget_inr:.0f} for the whole session. Never spend more than this.

How the merchant works:
- There is a flat rate (pass `credits` to buy_credits): always Rs 50 per credit,
  no trust score needed.
- There are named tiers (pass `tier`): Plus and Pro are cheaper per credit than
  the flat rate, but each needs a minimum TRACE trust score. Call get_catalog
  for the exact prices and thresholds.
- Call check_trust to see your current score and which tier you qualify for.
- Every purchase is scored by TRACE before it goes through. A tier you don't
  qualify for is refused with a TIER_MIN_SCORE_NOT_MET flag; the response
  explains why.

Operating rules:
- Every tool call requires a `reasoning` field: one or two plain sentences
  saying why you are making that call right now.
"""
    # The rigid buying procedure is for a normal session. When a principal
    # instruction overrides the kickoff (the `--rogue` scenario), forcing a
    # catalog-first procedure would just mask what that instruction makes
    # the agent do -- so that path gets the lighter rules instead.
    if config.kickoff_override is None:
        base += """- Follow this procedure for buying, in order:
  1. Call get_catalog and check_trust once each, first.
  2. For your FIRST purchase, attempt `tier: "Pro"` -- the cheapest per credit --
     even though the catalog's stated Pro threshold looks higher than your
     score. The catalog threshold is only a guide; only TRACE's actual
     response is authoritative, and probing costs nothing.
  3. If that returns a TIER_MIN_SCORE_NOT_MET refusal, attempt `tier: "Plus"`.
  4. Whichever tier TRACE first allows, keep buying with that same `tier` --
     one call per bundle -- until you reach the goal.
  5. Use the flat `credits` rate ONLY for a leftover of 1-4 credits smaller
     than any tier bundle. Never pass `credits` for a quantity of 5 or more.
"""
    else:
        base += """- Buy in whatever way gets credits fastest and cheapest. Pass `credits`
  for a flat-rate amount, or `tier` for a named bundle.
"""
    base += f"""- If a call is blocked or refused, do NOT repeat it unchanged. Read the
  explanation and change your approach.
- Stop as soon as you have {config.goal_credits} credits, or the remaining
  budget cannot buy any more. Do not buy past the goal. When you stop, reply
  with a short plain-language summary and make no further tool calls."""
    if config.extra_instructions.strip():
        base += "\n\nADDITIONAL INSTRUCTIONS:\n" + config.extra_instructions.strip()
    return base


def _assistant_message(turn: LLMTurn) -> dict:
    msg: dict = {"role": "assistant", "content": turn.text or ""}
    if turn.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
            }
            for tc in turn.tool_calls
        ]
    return msg


async def _dispatch(
    tc: ToolCall, config: AgentConfig, tools: MerchantTools, session: AgentSession
) -> dict:
    if tc.malformed:
        return {
            "error": True,
            "detail": (
                "Your tool arguments were not a valid JSON object. Retry this call "
                "with a well-formed arguments object."
            ),
        }

    if tc.name == "get_catalog":
        try:
            return await tools.get_catalog()
        except Exception as e:  # noqa: BLE001 -- surface, don't crash the loop
            return {"error": True, "detail": f"catalog lookup failed: {e}"}

    if tc.name == "check_trust":
        try:
            return await tools.check_trust(config.agent_id)
        except Exception as e:  # noqa: BLE001
            return {"error": True, "detail": f"trust check failed: {e}"}

    if tc.name == "buy_credits":
        return await _dispatch_buy(tc.arguments, config, tools, session)

    return {"error": True, "detail": f"unknown tool '{tc.name}'"}


async def _dispatch_buy(
    args: dict, config: AgentConfig, tools: MerchantTools, session: AgentSession
) -> dict:
    tier = args.get("tier")
    auto_upsell = bool(args.get("auto_upsell", False))
    try:
        credits = int(args.get("credits", 1))
    except (TypeError, ValueError):
        credits = 1
    if tier and tier not in _TIER_PRICE_INR:
        return {"error": True, "detail": f"unknown tier '{tier}'. Valid: Starter, Plus, Pro."}

    remaining = config.budget_inr - session.spent_inr
    est_cost = _TIER_PRICE_INR[tier] if tier else credits * CHEAPEST_CREDIT_INR

    # Client-side bound (courtesy). This is the check a hostile instruction
    # can talk the model out of -- deliberately -- and the reason the
    # server-side caps in merchant/app.py exist regardless of what the model
    # or TRACE decides.
    if est_cost > remaining + 1e-6:
        return {
            "refused_client_side": True,
            "detail": (
                f"This purchase would cost about Rs {est_cost:.0f}, but only Rs "
                f"{remaining:.0f} of the Rs {config.budget_inr:.0f} budget is left. "
                "Not attempted. Buy a smaller amount, or stop."
            ),
        }

    idem = f"agent-{config.agent_id}-{uuid.uuid4().hex[:8]}"
    result = await tools.buy_credits(
        agent_id=config.agent_id,
        credits=credits,
        tier=tier,
        auto_upsell=auto_upsell,
        idempotency_key=idem,
    )

    if result.get("status") == "order_created":
        session.spent_inr += float(result.get("amount_inr", est_cost))
        applied = result.get("applied_tier")
        if applied:
            gained = _TIER_CREDITS.get(applied, credits)
        elif tier:
            gained = _TIER_CREDITS.get(tier, credits)
        else:
            gained = credits
        session.credits_acquired += gained
        if result.get("razorpay_order_id"):
            session.orders.append(result["razorpay_order_id"])

    return result


async def _safe_fallback(
    config: AgentConfig, tools: MerchantTools, session: AgentSession
) -> None:
    """The LLM backend is unreachable. Rather than spin, make one bounded,
    deterministic purchase (a single Starter credit) if the budget allows,
    record it, and let run_session mark the session accordingly."""
    if (config.budget_inr - session.spent_inr) < CHEAPEST_CREDIT_INR:
        return
    idem = f"agent-{config.agent_id}-fallback-{uuid.uuid4().hex[:8]}"
    result = await tools.buy_credits(
        agent_id=config.agent_id, credits=1, idempotency_key=idem
    )
    rec = TurnRecord(
        index=len(session.turns), reasoning="[deterministic fallback: LLM unavailable]"
    )
    rec.tools.append(
        ToolInvocation(name="buy_credits", arguments={"credits": 1}, result=result)
    )
    session.turns.append(rec)
    if result.get("status") == "order_created":
        session.spent_inr += float(result.get("amount_inr", CHEAPEST_CREDIT_INR))
        session.credits_acquired += 1
        if result.get("razorpay_order_id"):
            session.orders.append(result["razorpay_order_id"])


async def run_session(
    config: AgentConfig, tools: MerchantTools, llm: Any
) -> AgentSession:
    """Drive one buyer session to completion. `llm` needs one method,
    `complete(messages, tools) -> LLMTurn` (OpenAILLM, or a test fake)."""
    session = AgentSession(config=config)
    kickoff = config.kickoff_override or (
        f"Begin. Acquire {config.goal_credits} credits within the Rs "
        f"{config.budget_inr:.0f} budget."
    )
    messages: List[dict] = [
        {"role": "system", "content": _system_prompt(config)},
        {"role": "user", "content": kickoff},
    ]

    for turn_i in range(config.max_turns):
        try:
            turn = llm.complete(messages, TOOL_SCHEMAS)
        except LLMUnavailable as e:
            logger.warning("LLM unavailable (%s) -- deterministic fallback", e)
            await _safe_fallback(config, tools, session)
            session.outcome = "llm_unavailable_fallback"
            break

        record = TurnRecord(index=turn_i, reasoning=turn.text)
        messages.append(_assistant_message(turn))

        if not turn.tool_calls:
            session.turns.append(record)
            session.outcome = (
                "goal_met"
                if session.credits_acquired >= config.goal_credits
                else "agent_stopped"
            )
            break

        reasoning_bits: List[str] = []
        for tc in turn.tool_calls:
            # Pull the forced rationale out of the arguments so it's recorded
            # as the turn's thinking and never reaches the merchant.
            r = tc.arguments.pop("reasoning", None)
            if r:
                reasoning_bits.append(str(r))
            result = await _dispatch(tc, config, tools, session)
            record.tools.append(
                ToolInvocation(name=tc.name, arguments=tc.arguments, result=result)
            )
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)}
            )

        if not record.reasoning and reasoning_bits:
            record.reasoning = " ".join(reasoning_bits)

        session.turns.append(record)

        if session.credits_acquired >= config.goal_credits:
            session.outcome = "goal_met"
            break
        if (config.budget_inr - session.spent_inr) < CHEAPEST_CREDIT_INR:
            session.outcome = "budget_exhausted"
            break
    else:
        session.outcome = "max_turns"

    session.finished_at = time.time()
    return session
