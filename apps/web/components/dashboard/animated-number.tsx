"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A number that counts up to its target when it first scrolls into view.
 *
 * Server-safe by construction: the first render (and the SSR HTML) shows the
 * final value, so there is never a hydration mismatch or a flash of "0". The
 * animation only starts on mount, and is skipped entirely under
 * `prefers-reduced-motion` - the value is simply already there.
 *
 * `format` receives the live interpolating value, so the caller owns how it is
 * presented (currency, plain integer, percent, ...).
 */
export default function AnimatedNumber({
  value,
  format,
  duration = 950,
  className,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
  className?: string;
}) {
  const [display, setDisplay] = useState(value);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (!Number.isFinite(value)) return;
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return; // display already holds the final value
    const from = 0;
    const begin = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - begin) / duration);
      const eased = 1 - Math.pow(1 - p, 3); // ease-out cubic
      setDisplay(from + (value - from) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return (
    <span className={className}>
      {format ? format(display) : Math.round(display).toLocaleString()}
    </span>
  );
}
