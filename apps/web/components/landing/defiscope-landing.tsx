"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  BellRing,
  LayoutGrid,
  MessageSquareText,
  ShieldCheck,
} from "lucide-react";

import { API_PUBLIC_URL } from "@/lib/api-config";

/* ---------------------------------------------------------------------------
   The film, verbatim. Two copies of the same file: the clip's last frame does
   not match its first, so a plain `loop` snaps a continent sideways every ten
   seconds. They ping-pong instead (see the cross-fade effect below), and the
   browser only fetches the asset once.
   ------------------------------------------------------------------------- */
const VIDEO_SRC =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260912_104036_bd6924f6-3c8e-417e-8465-6d03c8c2e9e6.mp4";
const POSTER_SRC =
  "https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/82e7eb75-c65f-490a-99b5-f3d1cad54200.webp";

/** The two copies take turns; this is the class the swap toggles. */
const ACTIVE = "ds-is-active";

/** One place to repoint the page once the real destinations exist. */
const LINKS = {
  login: "/login",
  board: "/login",
  about: "/about",
  docs: `${API_PUBLIC_URL}/docs`,
} as const;

/**
 * The four surfaces, each one a thing the backend actually does — not a
 * capability invented for a landing page. The wording is lifted from the
 * methodology and architecture docs so the page cannot promise more than the
 * pipeline delivers.
 */
const CAPABILITIES = [
  {
    icon: ShieldCheck,
    title: "Explainable scoring",
    text: "Seven weighted indicators: concentration, volatility, trend, incentives, audit posture, real yield and peg integrity. Every score ships with its evidence and its limitation.",
  },
  {
    icon: LayoutGrid,
    title: "Research board",
    text: "TVL, 7d/30d moves, fees, DEX volume and chain concentration across curated protocols plus the top 50 by TVL, all rendered DB-first from daily snapshots.",
  },
  {
    icon: BellRing,
    title: "Monitoring & alerts",
    text: "Six rules flag crashes, daily shocks, incentive-heavy structures, depegs and stale upstream data. Idempotent per protocol, rule and day, fanned out to Slack, Discord, Telegram, email or a webhook.",
  },
  {
    icon: MessageSquareText,
    title: "Ask the analyst",
    text: "Grounded Q&A over the methodology and each protocol's own evidence. Every answer cites numbered sources, or refuses when nothing relevant was retrieved.",
  },
] as const;

const STEPS = [
  {
    title: "Ingest",
    text: "DefiLlama packs are normalized to a daily, forward-filled UTC frame; Dune adds four contract-level activity metrics per chain, per day. A missing feed stays a gap.",
  },
  {
    title: "Score",
    text: "Each indicator maps its anchors onto 0 to 100 and carries a weight. Anything that cannot be computed leaves the composite and is listed under data_gaps instead.",
  },
  {
    title: "Monitor",
    text: "A 30-minute pass re-scores the watchlist, fires the rules with the metric, value and threshold that triggered them, and notifies the channels you configured.",
  },
] as const;

function Arrow({ className }: { className: string }) {
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

export function DeFiScopeLanding() {
  const videoARef = useRef<HTMLVideoElement>(null);
  const videoBRef = useRef<HTMLVideoElement>(null);
  const headerRef = useRef<HTMLElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const [stuck, setStuck] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  /* ---------------------------------------------------------------- entrance
     The reveal is gated on document.fonts.ready: with a block face the mask
     would otherwise animate against invisible glyphs and the headline would
     appear to finish before it starts. The timer is a safety net: a stalled
     font request must never leave the page permanently blank. -------------- */
  useEffect(() => {
    const root = rootRef.current;
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
      // The page may be left mid-entrance by a fast navigation; drop the flag so
      // a later mount starts from a clean state.
      delete root.dataset.landing;
    };
  }, []);

  /* ------------------------------------------------------------- cross-fade
     A and B ping-pong: the incoming copy starts at 0 and fades in while the
     outgoing one plays out its final FADE seconds. The overlap is scheduled
     FADE early so the fade *finishes* at the seam. ------------------------- */
  useEffect(() => {
    const a = videoARef.current;
    const b = videoBRef.current;
    if (!a || !b) return;

    const FADE = 0.9; // must match .ds-bg-video's transition duration
    const EDGE = 0.08; // timeupdate fires ~4×/s; schedule a hair early
    let showing = a;
    let parked: number | undefined;

    // React writes `muted` as an attribute; autoplay policy checks the property.
    a.muted = true;
    b.muted = true;

    const play = (el: HTMLVideoElement) => {
      try {
        const started = el.play();
        if (started) started.catch(() => {});
      } catch {
        // A decode race must never take the page down with it.
      }
    };

    const swap = () => {
      const next = showing === a ? b : a;
      const prev = showing;

      try {
        next.currentTime = 0;
      } catch {
        // Seeking an unbuffered element can throw; play() below still works.
      }
      play(next);

      next.classList.add(ACTIVE);
      prev.classList.remove(ACTIVE);
      showing = next;

      // Park the hidden copy: it would otherwise keep decoding frames for
      // nothing, which on a laptop is a measurable battery cost.
      parked = window.setTimeout(() => {
        try {
          prev.pause();
          prev.currentTime = 0;
        } catch {
          // Already detached — nothing to park.
        }
      }, FADE * 1000 + 60);
    };

    const tick = (event: Event) => {
      const video = event.currentTarget as HTMLVideoElement;
      if (video !== showing || video.readyState < 2) return;
      const { duration } = video;
      if (!Number.isFinite(duration) || duration <= FADE + EDGE) return;
      if (duration - video.currentTime <= FADE + EDGE) swap();
    };

    const onVisible = () => {
      if (!document.hidden && showing.paused) play(showing);
    };

    a.addEventListener("timeupdate", tick);
    b.addEventListener("timeupdate", tick);
    document.addEventListener("visibilitychange", onVisible);
    play(a);

    return () => {
      a.removeEventListener("timeupdate", tick);
      b.removeEventListener("timeupdate", tick);
      document.removeEventListener("visibilitychange", onVisible);
      if (parked !== undefined) window.clearTimeout(parked);
    };
  }, []);

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

  /* ------------------------------------------------------------- mobile menu */
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
      window.removeEventListener("resize", onResize);
    };
  }, [menuOpen]);

  const closeMenu = () => setMenuOpen(false);

  return (
    // `data-landing` ships in the server HTML on purpose: it is what holds the
    // hero back until the fonts are ready, and having it rendered (rather than
    // added later) keeps hydration honest — the effect below only flips the
    // value, it never introduces the attribute.
    <div className="ds-root" id="landing-root" ref={rootRef} data-landing="pending">
      <a className="ds-skip" href="#hero">
        Skip to content
      </a>

      <header
        ref={headerRef}
        className={stuck ? "ds-nav ds-nav-stuck" : "ds-nav"}
      >
        <a className="ds-logo" href="#landing-root">
          <span className="ds-logo-dot" aria-hidden="true" />
          DeFiScope<span className="ds-logo-ai">AI</span>
        </a>

        <nav className="ds-nav-links" aria-label="Primary">
          <a href="#platform">Platform</a>
          <a href="#how">How it works</a>
          <a href={LINKS.docs} target="_blank" rel="noreferrer">
            Docs
          </a>
          <Link href={LINKS.about}>About</Link>
        </nav>

        <div className="ds-nav-actions">
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
          <a href="#platform">Platform</a>
          <a href="#how">How it works</a>
          <a href={LINKS.docs} target="_blank" rel="noreferrer">
            Docs
          </a>
          <Link href={LINKS.about}>About</Link>
          <div className="ds-divider" />
          <Link href={LINKS.login}>Sign in</Link>
          <Link className="ds-m-start" href={LINKS.board}>
            Open the board
            <Arrow className="ds-arrow" />
          </Link>
        </nav>
      </header>

      <main>
        <section className="ds-hero" id="hero">
          <div
            className="ds-bg"
            role="img"
            aria-label="A stylised globe of Earth rendered as a green dot matrix against a starfield, slowly rotating"
          >
            <video
              ref={videoARef}
              className="ds-bg-video ds-is-active"
              poster={POSTER_SRC}
              autoPlay
              muted
              loop
              playsInline
              preload="auto"
              disablePictureInPicture
              aria-hidden="true"
              tabIndex={-1}
            >
              <source src={VIDEO_SRC} type="video/mp4" />
            </video>
            <video
              ref={videoBRef}
              className="ds-bg-video"
              poster={POSTER_SRC}
              muted
              loop
              playsInline
              preload="auto"
              disablePictureInPicture
              aria-hidden="true"
              tabIndex={-1}
            >
              <source src={VIDEO_SRC} type="video/mp4" />
            </video>
          </div>

          <div className="ds-tint" aria-hidden="true" />

          <div className="ds-hero-inner">
            <h1 className="ds-h1">
              <span className="ds-ln">
                <span className="ds-ln-inner">Protocol risk,</span>
              </span>
              <span className="ds-ln">
                <span className="ds-ln-inner">explained.</span>
              </span>
            </h1>

            <p className="ds-sub">
              Seven weighted indicators, scored from live DefiLlama data,
              <br />
              each one shipped with its evidence and what it cannot establish,
              <br />
              so a missing feed stays a gap, never a reassuring zero.
            </p>

            <div className="ds-ctas">
              <Link
                className="ds-btn ds-btn-lg ds-btn-primary"
                href={LINKS.board}
              >
                Open the board
                <Arrow className="ds-arrow" />
              </Link>
              <a className="ds-btn ds-btn-lg ds-btn-ghost" href="#how">
                See how it works
                <Arrow className="ds-arrow" />
              </a>
            </div>
          </div>
        </section>

        <section className="ds-section" id="platform">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">Platform</p>
            <h2 className="ds-h2">
              One board for the whole
              <br />
              <em>due-diligence</em> pass.
            </h2>
            <p className="ds-lede">
              A scored market board, per-protocol evidence, rule-based
              monitoring and a grounded analyst: four views over the same
              numbers. Every figure traces back to a pure function with a test
              behind it, not to a model&apos;s guess.
            </p>

            <ul className="ds-cards">
              {CAPABILITIES.map(({ icon: Icon, title, text }) => (
                <li className="ds-card" key={title}>
                  <span className="ds-card-icon" aria-hidden="true">
                    <Icon size={19} strokeWidth={1.6} />
                  </span>
                  <h3 className="ds-card-title">{title}</h3>
                  <p className="ds-card-text">{text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="ds-section ds-section-raise" id="how">
          <div className="ds-section-inner">
            <p className="ds-eyebrow">How it works</p>
            <h2 className="ds-h2">From raw aggregate to a defended number.</h2>

            <div className="ds-how-grid">
              <ol className="ds-steps">
                {STEPS.map(({ title, text }) => (
                  <li className="ds-step" key={title}>
                    <h3 className="ds-step-title">{title}</h3>
                    <p className="ds-step-text">{text}</p>
                  </li>
                ))}
              </ol>

              <pre className="ds-code" aria-label="Example protocol research response">
                <code>
                  <span className="ds-code-line">
                    <span className="ds-code-verb">GET</span> /api/protocols/aave-v3
                  </span>
                  <span className="ds-code-line">
                    <span className="ds-code-key">Authorization:</span> Bearer …
                  </span>
                  <span className="ds-code-line"> </span>
                  <span className="ds-code-line">{"{"}</span>
                  <span className="ds-code-line">
                    {"  "}
                    <span className="ds-code-key">{'"slug"'}</span>:{" "}
                    <span className="ds-code-str">{'"aave-v3"'}</span>,
                  </span>
                  <span className="ds-code-line">
                    {"  "}
                    <span className="ds-code-key">{'"as_of"'}</span>:{" "}
                    <span className="ds-code-str">{'"2026-10-30"'}</span>,
                  </span>
                  <span className="ds-code-line">
                    {"  "}
                    <span className="ds-code-key">{'"risk"'}</span>: {"{"}
                  </span>
                  <span className="ds-code-line">
                    {"    "}
                    <span className="ds-code-key">{'"composite_score"'}</span>:{" "}
                    <span className="ds-code-str">34.2</span>,
                  </span>
                  <span className="ds-code-line">
                    {"    "}
                    <span className="ds-code-key">{'"band"'}</span>:{" "}
                    <span className="ds-code-str">{'"moderate"'}</span>,
                  </span>
                  <span className="ds-code-line">
                    {"    "}
                    <span className="ds-code-key">{'"data_gaps"'}</span>: []
                  </span>
                  <span className="ds-code-line">{"  }"}</span>
                  <span className="ds-code-line">{"}"}</span>
                </code>
              </pre>
            </div>
          </div>
        </section>

        <section className="ds-section ds-contact" id="contact">
          <div className="ds-contact-inner">
            <h2 className="ds-contact-title">
              It flags the reason to investigate.
            </h2>
            <p className="ds-contact-text">
              DeFiScope never calls a protocol healthy because TVL rose. It
              scores what it can measure, shows what it could not, and tells you
              what to check next.
            </p>
            <div className="ds-contact-actions">
              <Link className="ds-btn ds-btn-primary" href={LINKS.board}>
                Open the board
                <Arrow className="ds-arrow" />
              </Link>
              <Link className="ds-btn ds-btn-ghost" href={LINKS.about}>
                Read the methodology
                <Arrow className="ds-arrow" />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="ds-footer">
        <div className="ds-footer-inner">
          {/* No `new Date()` here: under Cache Components that is an unstable
              value the prerender refuses to bake. The year adds nothing a
              copyright line needs. */}
          <span>© DeFiScope AI. Research, not investment advice.</span>
          <div className="ds-footer-links">
            <Link href={LINKS.about}>Methodology</Link>
            <a href={LINKS.docs} target="_blank" rel="noreferrer">
              API docs
            </a>
            <Link href={LINKS.login}>Sign in</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
