"use client";

import { useEffect, useState } from "react";

import {
  DOCS_GROUPS,
  DOCS_SECTIONS,
  DOCS_SUBHEADS,
  type DocsLink,
} from "./docs-data";

/* ===========================================================================
   The two rails of the docs reference.
   ---------------------------------------------------------------------------
   The left is the index (where am I in an 18-part manual); the right is
   "on this page" for just the section you are reading, plus a thread showing how
   much of it is left. Both track a scroll position, and only the browser knows
   that, so this is the one part of `/welcome/docs` that is a client component.

   The active item is derived from a scroll probe, not from `:target`: a reader's
   position is a range between two headings, and `:target` only fires on the one
   hash they clicked, so it would go stale the moment they scroll past it.
   ========================================================================= */

/** The line, measured from the top, a heading must clear to count as "passed". */
const SPY_OFFSET = 100;

function headingY(id: string): number {
  const el = document.getElementById(id);
  if (!el) return Number.POSITIVE_INFINITY;
  return el.getBoundingClientRect().top + window.scrollY - SPY_OFFSET;
}

/**
 * The id of the heading the reader is currently under: the last one whose top
 * edge has scrolled above the spy line. Recomputed on scroll (rAF-throttled) and
 * once on mount, so a deep link that lands mid-page is correct without a scroll.
 */
function useActiveHeading(ids: readonly string[]): string | null {
  const [active, setActive] = useState<string | null>(ids[0] ?? null);

  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      let current = ids[0] ?? null;
      for (const id of ids) {
        if (headingY(id) <= window.scrollY) current = id;
        else break;
      }
      // At the very bottom the last short section may not reach the spy line;
      // pin it so the rail never sits on the previous section.
      if (
        window.innerHeight + window.scrollY >=
        document.documentElement.scrollHeight - 2
      ) {
        current = ids[ids.length - 1] ?? current;
      }
      setActive(current);
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
    // ids is a stable module array; re-running only when its identity changes.
  }, [ids]);

  return active;
}

/** Share a single scroll subscription for the reading-progress thread. */
function useReadProgress(): number {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      const doc = document.documentElement;
      const scrollable = doc.scrollHeight - window.innerHeight;
      setProgress(scrollable > 0 ? Math.min(1, window.scrollY / scrollable) : 1);
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);
  return progress;
}

/* ---------------------------------------------------------------- left rail */
export function DocsSideNav() {
  const ids = DOCS_SECTIONS.map((s) => s.id);
  const active = useActiveHeading(ids);

  return (
    <nav className="ds-docs-side" aria-label="Documentation sections">
      {DOCS_GROUPS.map((group) => (
        <div className="ds-docs-nav-group" key={group.title}>
          <p className="ds-docs-nav-title">{group.title}</p>
          {group.links.map((link: DocsLink) => (
            <a
              key={link.id}
              href={`#${link.id}`}
              className={
                active === link.id
                  ? "ds-docs-link ds-docs-link-active"
                  : "ds-docs-link"
              }
              aria-current={active === link.id ? "true" : undefined}
            >
              <span className="ds-docs-link-n">{link.n}</span>
              <span>{link.label}</span>
            </a>
          ))}
        </div>
      ))}
    </nav>
  );
}

/* --------------------------------------------------------------- right rail */
export function DocsToc() {
  const ids = DOCS_SECTIONS.map((s) => s.id);
  const activeSection = useActiveHeading(ids);
  const progress = useReadProgress();

  const subs = activeSection ? (DOCS_SUBHEADS[activeSection] ?? []) : [];
  const subIds = subs.map((s) => s.href);
  const activeSub = useActiveHeading(subIds);

  const section = DOCS_SECTIONS.find((s) => s.id === activeSection);

  return (
    <aside className="ds-docs-aside" aria-label="On this page">
      <p className="ds-docs-aside-title">On this page</p>
      {subs.length > 0 ? (
        <ul className="ds-docs-toc">
          {subs.map((sub) => (
            <li key={sub.href}>
              <a
                href={`#${sub.href}`}
                aria-current={activeSub === sub.href ? "true" : undefined}
                style={
                  activeSub === sub.href
                    ? {
                        borderLeftColor: "var(--accent)",
                        color: "var(--ink)",
                      }
                    : undefined
                }
              >
                {sub.label}
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className="ds-docs-aside-title" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 400, fontSize: "12.5px" }}>
          {section ? section.label : "Contents"}
        </p>
      )}
      <div
        className="ds-docs-progress"
        role="presentation"
        aria-hidden="true"
      >
        <i style={{ transform: `scaleX(${progress})` }} />
      </div>
    </aside>
  );
}
