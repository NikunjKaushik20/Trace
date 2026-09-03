import type { Metadata } from "next";
import TryItForm from "./TryItForm";

export const metadata: Metadata = {
  title: "Try It Live",
  description:
    "Score a real purchase against the live TRACE engine, not a mock. Pick an agent, see the score, the flags, and the plain-language explanation.",
};

export default function TryItPage() {
  return <TryItForm />;
}
