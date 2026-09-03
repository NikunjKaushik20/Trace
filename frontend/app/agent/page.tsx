import type { Metadata } from "next";
import AgentTheatre from "./AgentTheatre";

export const metadata: Metadata = {
  title: "The AI Buyer Agent",
  description:
    "A GPT-4o-mini agent given a goal and a hard budget, driving real purchases through TRACE. It holds the reasoning, never the purse strings — every bound is enforced where the money moves. Watch the honest run and the compromised one.",
};

export default function AgentPage() {
  return <AgentTheatre />;
}
