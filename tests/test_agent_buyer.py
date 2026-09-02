"""
Unit tests for the autonomous buyer agent (buildathon/agent/buyer.py).

No network, no OpenAI key: the LLM is a scripted fake (ScriptedLLM) that
replays a fixed sequence of turns, and the merchant tools are a fake that
returns canned responses and records calls -- same pattern as
test_merchant_app.py's FakeGate / FakeRazorpay.

Run from the Trace-API repo root:
    pytest buildathon/tests/test_agent_buyer.py -v
"""
from types import SimpleNamespace

import pytest

from buildathon.agent.buyer import (
    AgentConfig,
    LLMTurn,
    LLMUnavailable,
    ToolCall,
    _parse_openai_message,
    run_session,
)

_TIER = {"Starter": (1, 50.0), "Plus": (5, 225.0), "Pro": (20, 800.0)}


class ScriptedLLM:
    """Replays `turns` one per complete() call. An entry that is an
    Exception instance is raised instead of returned. When the script runs
    out, returns a no-tool-call turn (which ends the loop)."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        if self._turns:
            nxt = self._turns.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        return LLMTurn(text="Done.", tool_calls=[])


class FakeTools:
    def __init__(self, catalog=None, trust=None, buy_results=None):
        self._catalog = catalog or {
            "tiers": [
                {"name": "Starter", "credits": 1, "price_inr": 50.0, "min_trust_score": 0.0},
                {"name": "Plus", "credits": 5, "price_inr": 225.0, "min_trust_score": 0.25},
                {"name": "Pro", "credits": 20, "price_inr": 800.0, "min_trust_score": 0.5},
            ]
        }
        self._trust = trust or {
            "score": 0.35,
            "routing_decision": "ROUTE_WITH_CAUTION",
            "flags": [],
            "unlocked_tier": "Plus",
        }
        # Consumed in order; the last entry repeats once exhausted.
        self._buy_results = list(buy_results or [])
        self.catalog_calls = 0
        self.trust_calls = 0
        self.buy_calls = []

    async def get_catalog(self):
        self.catalog_calls += 1
        return self._catalog

    async def check_trust(self, agent_id):
        self.trust_calls += 1
        return dict(self._trust, agent_id=agent_id)

    async def buy_credits(self, agent_id, credits=1, tier=None, auto_upsell=False, idempotency_key=None):
        self.buy_calls.append(
            {"agent_id": agent_id, "credits": credits, "tier": tier, "auto_upsell": auto_upsell}
        )
        if self._buy_results:
            return self._buy_results.pop(0) if len(self._buy_results) > 1 else self._buy_results[0]
        # Computed default: honor tier, otherwise flat rate.
        if tier:
            c, amt = _TIER[tier]
        else:
            c, amt = credits, credits * 50.0
        return {
            "status": "order_created",
            "amount_inr": amt,
            "routing_decision": "ROUTE",
            "score": 0.8,
            "applied_tier": tier,
            "razorpay_order_id": f"order_{len(self.buy_calls)}",
        }

    async def close(self):
        pass


def _buy(**args):
    return ToolCall(id=f"tc_{args}", name="buy_credits", arguments=args)


def _cfg(**over):
    base = dict(agent_id="agent_honest_0", buyer_name="Test", goal_credits=13, budget_inr=1000.0)
    base.update(over)
    return AgentConfig(**base)


@pytest.mark.asyncio
async def test_happy_path_reaches_goal_and_tracks_spend():
    llm = ScriptedLLM(
        [
            LLMTurn("Checking the catalog.", [ToolCall("t1", "get_catalog", {})]),
            LLMTurn("Score 0.35 unlocks Plus. Buying Plus.", [_buy(tier="Plus")]),
            LLMTurn("Five more with Plus.", [_buy(tier="Plus")]),
            LLMTurn("Three more via flat rate.", [_buy(credits=3)]),
            LLMTurn("Goal met.", []),
        ]
    )
    tools = FakeTools()
    session = await run_session(_cfg(goal_credits=13), tools, llm)

    assert session.outcome == "goal_met"
    assert session.credits_acquired == 13  # 5 + 5 + 3
    assert session.spent_inr == pytest.approx(225.0 + 225.0 + 150.0)
    assert len(session.orders) == 3


@pytest.mark.asyncio
async def test_client_side_budget_refuses_overspend_without_calling_merchant():
    llm = ScriptedLLM([LLMTurn("Buying big.", [_buy(credits=50)]), LLMTurn("Stopping.", [])])
    tools = FakeTools()
    session = await run_session(_cfg(goal_credits=50, budget_inr=100.0), tools, llm)

    assert tools.buy_calls == []  # never reached the merchant
    assert session.turns[0].tools[0].result.get("refused_client_side") is True
    assert session.spent_inr == 0.0


@pytest.mark.asyncio
async def test_server_cap_rejection_is_surfaced_not_raised():
    llm = ScriptedLLM(
        [LLMTurn("50 flat.", [_buy(credits=50)]), LLMTurn("Understood, can't. Stopping.", [])]
    )
    tools = FakeTools(
        buy_results=[
            {
                "error": True,
                "status_code": 400,
                "detail": "credits (50) exceeds the per-purchase cap of 20",
            }
        ]
    )
    # Budget high enough that the client-side check passes and the request
    # actually reaches the (faked) merchant, which rejects it on the cap.
    session = await run_session(_cfg(goal_credits=50, budget_inr=100_000.0), tools, llm)

    assert len(tools.buy_calls) == 1
    res = session.turns[0].tools[0].result
    assert res["error"] is True and res["status_code"] == 400
    assert session.credits_acquired == 0
    assert session.outcome in ("agent_stopped", "max_turns")


@pytest.mark.asyncio
async def test_malformed_tool_arguments_do_not_crash_the_loop():
    bad = ToolCall("t1", "buy_credits", {}, malformed=True)
    llm = ScriptedLLM([LLMTurn("buying", [bad]), LLMTurn("done", [])])
    tools = FakeTools()
    session = await run_session(_cfg(goal_credits=1, budget_inr=100.0), tools, llm)

    assert tools.buy_calls == []
    res = session.turns[0].tools[0].result
    assert res["error"] is True
    assert "JSON" in res["detail"]


@pytest.mark.asyncio
async def test_max_turns_terminates_the_loop():
    forever = [LLMTurn("again", [ToolCall(f"t{i}", "get_catalog", {})]) for i in range(50)]
    llm = ScriptedLLM(forever)
    tools = FakeTools()
    session = await run_session(_cfg(goal_credits=999, budget_inr=100.0, max_turns=5), tools, llm)

    assert session.outcome == "max_turns"
    assert len(session.turns) == 5
    assert llm.calls == 5


@pytest.mark.asyncio
async def test_llm_unavailable_falls_back_to_one_bounded_purchase():
    llm = ScriptedLLM([LLMUnavailable("openai down")])
    tools = FakeTools()
    session = await run_session(_cfg(goal_credits=10, budget_inr=100.0), tools, llm)

    assert session.outcome == "llm_unavailable_fallback"
    assert len(tools.buy_calls) == 1
    assert tools.buy_calls[0]["credits"] == 1 and tools.buy_calls[0]["tier"] is None
    assert session.credits_acquired == 1


@pytest.mark.asyncio
async def test_fallback_does_nothing_when_budget_cannot_afford_a_credit():
    llm = ScriptedLLM([LLMUnavailable("down")])
    tools = FakeTools()
    session = await run_session(_cfg(goal_credits=1, budget_inr=10.0), tools, llm)  # < Rs 50

    assert session.outcome == "llm_unavailable_fallback"
    assert tools.buy_calls == []


@pytest.mark.asyncio
async def test_stops_at_goal_even_if_the_model_wants_to_keep_buying():
    llm = ScriptedLLM([LLMTurn("buy Plus", [_buy(tier="Plus")]), LLMTurn("buy more", [_buy(tier="Plus")])])
    tools = FakeTools()
    session = await run_session(_cfg(goal_credits=5, budget_inr=100_000.0), tools, llm)

    assert session.outcome == "goal_met"
    assert len(tools.buy_calls) == 1
    assert session.credits_acquired == 5


@pytest.mark.asyncio
async def test_auto_upsell_applied_tier_drives_the_credit_tally():
    llm = ScriptedLLM([LLMTurn("one credit, allow upsell", [_buy(credits=1, auto_upsell=True)]), LLMTurn("done", [])])
    tools = FakeTools(
        buy_results=[
            {
                "status": "order_created",
                "amount_inr": 225.0,
                "routing_decision": "ROUTE_WITH_CAUTION",
                "score": 0.4,
                "applied_tier": "Plus",
                "upsell_applied": True,
                "razorpay_order_id": "order_up",
            }
        ]
    )
    session = await run_session(_cfg(goal_credits=5, budget_inr=1000.0), tools, llm)

    assert session.credits_acquired == 5  # from applied_tier "Plus", not the requested 1
    assert session.spent_inr == pytest.approx(225.0)
    assert session.outcome == "goal_met"


@pytest.mark.asyncio
async def test_forced_reasoning_argument_becomes_the_turn_reasoning_and_is_stripped():
    llm = ScriptedLLM(
        [
            LLMTurn(None, [_buy(tier="Plus", reasoning="Score 0.35 unlocks Plus; best price I qualify for.")]),
            LLMTurn("done", []),
        ]
    )
    tools = FakeTools()
    session = await run_session(_cfg(goal_credits=5, budget_inr=1000.0), tools, llm)

    # surfaced as the turn's thinking even though assistant content was None
    assert session.turns[0].reasoning == "Score 0.35 unlocks Plus; best price I qualify for."
    # stripped before the merchant call and out of the audit record's arguments
    assert "reasoning" not in tools.buy_calls[0]
    assert "reasoning" not in session.turns[0].tools[0].arguments


@pytest.mark.asyncio
async def test_session_as_dict_has_the_audit_shape():
    llm = ScriptedLLM([LLMTurn("hi", [ToolCall("t1", "get_catalog", {})]), LLMTurn("done", [])])
    tools = FakeTools()
    session = await run_session(_cfg(goal_credits=1, budget_inr=100.0), tools, llm)
    d = session.as_dict()

    assert set(d) >= {
        "config",
        "outcome",
        "credits_acquired",
        "spent_inr",
        "budget_remaining_inr",
        "razorpay_orders",
        "turns",
        "duration_s",
    }
    assert d["turns"][0]["tools"][0]["name"] == "get_catalog"
    assert d["config"]["agent_id"] == "agent_honest_0"


def test_parse_openai_message_flags_malformed_json_arguments():
    msg = SimpleNamespace(
        content="reasoning here",
        tool_calls=[
            SimpleNamespace(
                id="c1",
                function=SimpleNamespace(name="buy_credits", arguments="{not valid json"),
            )
        ],
    )
    turn = _parse_openai_message(msg)
    assert turn.text == "reasoning here"
    assert turn.tool_calls[0].malformed is True
    assert turn.tool_calls[0].arguments == {}


def test_parse_openai_message_parses_a_valid_tool_call():
    msg = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                id="c1", function=SimpleNamespace(name="get_catalog", arguments="{}")
            )
        ],
    )
    turn = _parse_openai_message(msg)
    assert turn.text is None
    assert turn.tool_calls[0].name == "get_catalog"
    assert turn.tool_calls[0].malformed is False


def test_parse_openai_message_plain_text_no_tools():
    msg = SimpleNamespace(content="I have enough credits now.", tool_calls=None)
    turn = _parse_openai_message(msg)
    assert turn.text == "I have enough credits now."
    assert turn.tool_calls == []
