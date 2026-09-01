"""
Autonomous AI buyer agent for the Buildathon merchant demo.

An LLM (OpenAI gpt-4o-mini by default) is given a goal and a hard budget
and drives the real merchant purchase flow -- reading the catalog,
checking its own TRACE trust score, choosing a tier, buying, seeing
whether TRACE allowed it, and adapting. The LLM is the buyer's brain
only: it never scores anything and has no tool that bypasses /buy-credits.
See ../NOTES.md #18.
"""
