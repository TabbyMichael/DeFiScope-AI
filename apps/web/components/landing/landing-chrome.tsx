"use client";

import Link from "next/link";
import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { LINKS } from "./links";

/* ---------------------------------------------------------------------------
   The shared chrome of the public site.
   ----------------------------------------------------------------------------
   `/welcome` and `/welcome/about` are two documents that have to read as one
   product, so the bar, the footer and the entrance flag live here rather than
   being copied. Everything in this file is presentational: no session, no API
   read, no data. That is what keeps both pages prerenderable as static HTML.
   ------------------------------------------------------------------------- */

/** The little right arrow that rides inside the landing buttons. */
export function Arrow({ className }: { className: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 12 10"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M0.8 5h10M7.1 1.4 10.9 5l-3.8 3.6"
        stroke="currentColor"
        strokeWidth="1.35"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/**
 * Flips `data-landing` from `pending` to `ready` once the webfonts have settled.
 *
 * The reveal is gated on `document.fonts.ready`: the headline is animated
 * through a clip box, and with a block face the mask would animate against
 * invisible glyphs so the headline would appear to finish before it starts. The
 * timer is a safety net: a stalled font request must never leave the page
 * permanently blank.
 *
 * It renders nothing and finds the root by id, which lets the server hold the
 * markup (and the `pending` attribute that ships in the HTML) while this stays
 * the only thing that runs the choreography.
 */
export function LandingReveal({ rootId = "landing-root" }: { rootId?: string }) {
  useEffect(() => {
    const root = document.getElementById(rootId);
    if (!root) return;

    let settled = false;
    let timer: number | undefined;

    const reveal = () => {
      if (settled) return;
      settled = true;
      root.dataset.landing = "ready";
    };

    if (typeof document.fonts?.ready?.then === "function") {
      document.fonts.ready.then(reveal, reveal);
      timer = window.setTimeout(reveal, 1500);
    } else {
      reveal();
    }

    return () => {
      settled = true;
      if (timer !== undefined) window.clearTimeout(timer);
      // A page can be left mid-entrance by a fast navigation; drop the flag so
      // a later mount starts from a clean state.
      delete root.dataset.landing;
    };
  }, [rootId]);

  return null;
}

/** Where the nav's own section links point: same page on the landing, across
 *  pages everywhere else. */
type NavAnchors = { platform: string; how: string };

/** Which public document the visitor is reading, so the bar can mark it. */
type NavCurrent = "home" | "about" | "docs";

/**
 * The theme switch.
 *
 * It deliberately does not read the current theme during render: both glyphs
 * are in the DOM and the stylesheet picks one, so the server HTML and the first
 * client paint agree whatever the visitor chose last time. The click handler is
 * free to ask the document, because by then it is definitely there.
 */
function LandingThemeToggle() {
  const { setTheme } = useTheme();

  return (
    <button
      type="button"
      className="ds-theme"
      aria-label="Switch between the light and dark theme"
      onClick={() =>
        setTheme(
          document.documentElement.classList.contains("light")
            ? "dark"
            : "light",
        )
      }
    >
      <Sun
        className="ds-theme-sun"
        size={16}
        strokeWidth={1.7}
        aria-hidden="true"
      />
      <Moon
        className="ds-theme-moon"
        size={16}
        strokeWidth={1.7}
        aria-hidden="true"
      />
      <span className="ds-theme-label">Theme</span>
    </button>
  );
}

export function LandingNav({
  current,
  anchors,
}: {
  current: NavCurrent;
  anchors: NavAnchors;
}) {
  const headerRef = useRef<HTMLElement>(null);
  const [stuck, setStuck] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  /* ----------------------------------------------------------------- the bar
     The nav starts transparent over the film and picks up a translucent bar
     once the page has moved, so it stays legible over the sections. -------- */
  useEffect(() => {
    let frame = 0;
    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        setStuck(window.scrollY > 24);
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  /* ------------------------------------------------------------ mobile menu */
  useEffect(() => {
    if (!menuOpen) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!headerRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    // Resizing up to desktop hides the panel via CSS; drop the state too so the
    // burger is not left claiming aria-expanded="true".
    const onResize = () => {
      if (window.innerWidth > 1160) setMenuOpen(false);
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("resize", onResize);
    };
  }, [menuOpen]);

  const closeMenu = () => setMenuOpen(false);

  // On the landing page the logo is a scroll to top; on any other page it is a
  // navigation, because there is nothing above this document to scroll back to.
  const homeHref = current === "home" ? "#landing-root" : LINKS.home;

  return (
    <header ref={headerRef} className={stuck ? "ds-nav ds-nav-stuck" : "ds-nav"}>
      <Link className="ds-logo" href={homeHref}>
        <span className="ds-logo-dot" aria-hidden="true" />
        DeFiScope<span className="ds-logo-ai">AI</span>
      </Link>

      <nav className="ds-nav-links" aria-label="Primary">
        <a href={anchors.platform}>Platform</a>
        <a href={anchors.how}>How it works</a>
        <Link
          href={LINKS.docs}
          aria-current={current === "docs" ? "page" : undefined}
        >
          Docs
        </Link>
        <Link
          href={LINKS.about}
          aria-current={current === "about" ? "page" : undefined}
        >
          About
        </Link>
      </nav>

      <div className="ds-nav-actions">
        <LandingThemeToggle />
        <Link className="ds-btn ds-btn-login" href={LINKS.login}>
          Sign in
        </Link>
        <Link className="ds-btn ds-btn-nav-start" href={LINKS.board}>
          Open the board
          <Arrow className="ds-arrow" />
        </Link>
      </div>

      <button
        type="button"
        className={menuOpen ? "ds-burger ds-burger-open" : "ds-burger"}
        aria-label={menuOpen ? "Close menu" : "Open menu"}
        aria-expanded={menuOpen}
        aria-controls="landing-menu"
        onClick={() => setMenuOpen((open) => !open)}
      >
        <span className="ds-burger-bars" />
      </button>

      <nav
        id="landing-menu"
        className={menuOpen ? "ds-menu ds-menu-open" : "ds-menu"}
        aria-label="Mobile"
        onClick={closeMenu}
      >
        <a href={anchors.platform}>Platform</a>
        <a href={anchors.how}>How it works</a>
        <Link
          href={LINKS.docs}
          aria-current={current === "docs" ? "page" : undefined}
        >
          Docs
        </Link>
        <Link
          href={LINKS.about}
          aria-current={current === "about" ? "page" : undefined}
        >
          About
        </Link>
        <div className="ds-divider" />
        <Link href={LINKS.login}>Sign in</Link>
        <Link className="ds-m-start" href={LINKS.board}>
          Open the board
          <Arrow className="ds-arrow" />
        </Link>
        <LandingThemeToggle />
      </nav>
    </header>
  );
}

export function LandingFooter() {
  return (
    <footer className="ds-footer">
      <div className="ds-footer-inner">
        {/* No `new Date()` here: under Cache Components that is an unstable
            value the prerender refuses to bake. The year adds nothing a
            copyright line needs. */}
        <span>© DeFiScope AI. Research, not investment advice.</span>
        <div className="ds-footer-links">
          <Link href={LINKS.about}>About</Link>
          <Link href={LINKS.docs}>Docs</Link>
          <Link href={LINKS.methodology}>Methodology</Link>
          <a href={LINKS.api_reference} target="_blank" rel="noreferrer">
            OpenAPI reference
          </a>
          <a href={LINKS.repo} target="_blank" rel="noreferrer">
            Source
          </a>
          <Link href={LINKS.login}>Sign in</Link>
        </div>
      </div>
    </footer>
  );
}
