import type { Metadata } from "next";
import Link from "next/link";

import {
  Arrow,
  LandingFooter,
  LandingNav,
  LandingReveal,
} from "@/components/landing/landing-chrome";
import { LandingFilm } from "@/components/landing/landing-film";
import { LINKS } from "@/components/landing/links";
import { DocsSideNav, DocsToc } from "@/components/docs/docs-rails";
import { StartSections } from "@/components/docs/docs-part-start";
import { MethodSections } from "@/components/docs/docs-part-method";
import { MonitorSections } from "@/components/docs/docs-part-monitor";
import { OperateSections } from "@/components/docs/docs-part-operate";

/* ===========================================================================
   The documentation. One long reference, not a multi-route site.
   ---------------------------------------------------------------------------
   A reader arrives with a question and leaves with a number they can check, so
   the page is three columns: a numbered rail to jump from, the reference itself,
   and an "on this page" rail that tracks where you are. The rails are the only
   client code (they watch scroll); every section of prose is a server component
   and every figure is written from the code it documents, exactly as the About
   page does it.

   It reads no cookie and calls no API, so it prerenders to static HTML like the
   rest of `/welcome` and cannot fail because a backend is cold. The Docs link in
   the nav points here rather than to the Swagger page: a manual, not an endpoint
   index.
   ========================================================================= */

export const metadata: Metadata = {
  title: {
    absolute: "Docs: the DeFiScope AI reference",
  },
  description:
    "The full DeFiScope AI manual: how to run the stack, the seven weighted indicators and their anchors, the metric primitives, the alert rules, the data sources and their limits, the on-chain layer, the API surface, the access model, the configuration and the glossary.",
  openGraph: {
    title: "DeFiScope AI documentation",
    description:
      "Every number in DeFiScope traces to a pure function and a documented anchor. This is the reference: setup, methodology, rules, API, access model and limits.",
    type: "article",
  },
};

/* A jump row in the hero, one entry per rail group, pointing at its first
   section. The rail itself lists all eighteen. */
const GROUPS = [
  { href: "#overview", label: "Start here" },
  { href: "#architecture", label: "How a score is built" },
  { href: "#rules", label: "Monitoring" },
  { href: "#api", label: "Reference" },
] as const;

export default function DocsPage() {
  return (
    <div className="ds-root ds-doc" id="landing-root" data-landing="pending">
      <LandingReveal />

      <a className="ds-skip" href="#docs-main">
        Skip to content
      </a>

      <LandingNav
        current="docs"
        anchors={{ platform: LINKS.platform, how: LINKS.how }}
      />

      <main id="docs-main">
        <section className="ds-page-hero ds-docs-hero" id="hero">
          <div className="ds-page-bg" aria-hidden="true" />
          <LandingFilm className="ds-page-film" />
          <div className="ds-page-tint" aria-hidden="true" />
          <div className="ds-page-hero-inner">
            <p className="ds-eyebrow">Documentation</p>

            <h1 className="ds-h1">
              <span className="ds-ln">
                <span className="ds-ln-inner">The reference,</span>
              </span>
              <span className="ds-ln">
                <span className="ds-ln-inner">in full.</span>
              </span>
            </h1>

            <p className="ds-sub">
              Every number in DeFiScope traces to a pure function, a documented
              <br />
              anchor and a named limitation. This manual is that chain, written out:
              <br />
              how to run it, how a score is built, and what none of it can prove.
            </p>

            <div className="ds-ctas">
              <Link className="ds-btn ds-btn-lg ds-btn-primary" href="#getting-started">
                Run the stack
                <Arrow className="ds-arrow" />
              </Link>
              <a className="ds-btn ds-btn-lg ds-btn-ghost" href={LINKS.api_reference}>
                OpenAPI reference
                <Arrow className="ds-arrow" />
              </a>
            </div>

            <nav className="ds-chips" aria-label="Docs sections">
              {GROUPS.map(({ href, label }) => (
                <a key={href} href={href}>
                  {label}
                </a>
              ))}
            </nav>
          </div>
        </section>

        <div className="ds-docs-shell">
          <DocsSideNav />

          <div className="ds-docs-content">
            <StartSections />
            <MethodSections />
            <MonitorSections />
            <OperateSections />
          </div>

          <DocsToc />
        </div>

        <section className="ds-section ds-contact" aria-labelledby="docs-next-h">
          <div className="ds-contact-inner">
            <h2 className="ds-contact-title" id="docs-next-h">
              Read the numbers yourself.
            </h2>
            <p className="ds-contact-text">
              The weights live in the scoring module, the thresholds in the config,
              the formulas behind tested functions. If anything on this page does not
              match the code, the code is right and this page is the bug.
            </p>
            <div className="ds-contact-actions">
              <Link className="ds-btn ds-btn-primary" href={LINKS.board}>
                Open the board
                <Arrow className="ds-arrow" />
              </Link>
              <Link className="ds-btn ds-btn-ghost" href={LINKS.about}>
                The long-form About
                <Arrow className="ds-arrow" />
              </Link>
              <Link className="ds-btn ds-btn-ghost" href={LINKS.home}>
                Back to the platform
                <Arrow className="ds-arrow" />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <LandingFooter />
    </div>
  );
}
