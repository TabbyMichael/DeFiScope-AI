import type { Metadata, Viewport } from "next";
import { Plus_Jakarta_Sans } from "next/font/google";

// Global (not a CSS module) on purpose — see the header of the file.
import "./landing.css";

/**
 * The public landing page.
 *
 * It lives outside the (dashboard) group on purpose: no sidebar, no session, no
 * API calls — the same reasoning as `app/login/page.tsx`. The marketing page
 * must render for a visitor whose only credential is curiosity.
 *
 * The typeface is scoped here instead of the root layout so the product's Geist
 * stack stays untouched. `display: "block"` is deliberate: the hero's entrance
 * waits on `document.fonts.ready`, so a long swap period would animate the mask
 * against invisible glyphs.
 */
const display = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "800"],
  variable: "--font-display",
  display: "block",
});

export const metadata: Metadata = {
  title: "DeFiScope AI: Protocol risk, explained",
  description:
    "DeFi protocol research, explainable risk scoring and automated monitoring. Seven weighted indicators scored from live DefiLlama data, each shipped with its evidence and its limitations.",
  openGraph: {
    title: "DeFiScope AI: Protocol risk, explained",
    description:
      "Explainable risk scoring, automated monitoring and grounded research briefs for DeFi protocols.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#050807",
  colorScheme: "dark",
};

export default function WelcomeLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className={display.variable}>
      {children}
      {/*
        Flag the hero before the first paint. The entrance states are scoped to
        `[data-landing="pending"]`, so a visitor without JavaScript, or one
        whose bundle never hydrates, sees finished text rather than a
        permanently masked headline. The script sits *after* the markup it flags
        and is inline, so the parser cannot paint in between.
      */}
      <script
        dangerouslySetInnerHTML={{
          __html:
            "document.getElementById('landing-root')?.setAttribute('data-landing','pending')",
        }}
      />
    </div>
  );
}
