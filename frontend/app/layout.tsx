import type { Metadata } from "next";
import { Petrona, Work_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Nav } from "./components/Nav";
import { Footer } from "./components/Footer";

const petrona = Petrona({
  variable: "--font-petrona",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
});

const workSans = Work_Sans({
  variable: "--font-work-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const SITE_URL = "https://trace.example";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "TRACE: Trust Scoring for Autonomous AI Purchases",
    template: "%s · TRACE",
  },
  description:
    "TRACE scores every autonomous AI-agent purchase in real time using Bayesian confidence bounds, change-point detection, and graph-based Sybil defense, then explains the decision in plain language before a rupee moves.",
  keywords: [
    "AI agent payments",
    "agentic commerce trust",
    "fraud detection",
    "Sybil detection",
    "trust scoring API",
    "autonomous purchase risk",
    "agent-to-agent commerce",
  ],
  openGraph: {
    title: "TRACE: Trust Scoring for Autonomous AI Purchases",
    description:
      "Real-time trust scoring for autonomous AI purchases: explainable, bounded, and gated before money moves.",
    url: SITE_URL,
    siteName: "TRACE",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "TRACE: Trust Scoring for Autonomous AI Purchases",
    description:
      "Real-time trust scoring for autonomous AI purchases: explainable, bounded, and gated before money moves.",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout(props: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${petrona.variable} ${workSans.variable} ${jetbrainsMono.variable} h-full`}
    >
      <body className="min-h-full bg-paper text-ink">
        {/*
          React has no intrinsic way to emit a literal HTML comment node
          as a direct child (an ordinary JSX comment is stripped at
          compile time, dev and prod alike, and never reaches the DOM at
          all) -- so the direction contract below is injected via
          dangerouslySetInnerHTML into a zero-footprint (display:contents)
          wrapper, the closest a React app can get to "first child of
          body carries the contract" while still surviving `next build`
          and remaining grep-able in the shipped HTML.
        */}
        <div
          style={{ display: "contents" }}
          suppressHydrationWarning
          dangerouslySetInnerHTML={{
            __html: `<!--
THESIS: trust isn't asserted, it's grown and witnessed -- TRACE reads as
a warm, hand-kept ledger of provenance, refusing the generic dark
fintech-terminal look entirely.
OWN-WORLD: cashmere paper ground; sienna and deep bush-green as the two
committed colors carrying whole regions, oak as a third warm neutral,
one cool teal reserved for live data; frosted glass used specifically
as a "verification" material over textured/illustrated grounds; a
mycelial root-network motif for the trust graph; Petrona serif display
+ Work Sans + tabular JetBrains Mono for real numbers only.
STORY: a visitor understands within the hero that TRACE makes AI-agent
trust provable, not asserted, sees one real captured decision in place,
and wants to try it live.
FIRST VIEWPORT: full-bleed textured hero, serif thesis headline, an
authored root-network diagram animating in behind a glass "live
decision" panel showing a real captured quarantine decision -- proof in
place, not a generic hero shot.
FORM: editorial maximalist glassmorphic ledger -- pinned directly from
the user's brief (three reference palettes, explicit maximalism +
visible glassmorphism + light theme), not drawn from the concept-seed
roll; disclosed to the user as a deliberate substitution given how
specific the brief already was.
FINISH: unreviewed and undocumented is unfinished; this build ends with
the finish review, the verdict, DESIGN.md, and every shipping raster
carrying its provenance.
-->`,
          }}
        />
        <Nav />
        <main className="relative z-[1]">{props.children}</main>
        <Footer />
      </body>
    </html>
  );
}
