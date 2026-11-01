"use client";

import { useEffect, useRef } from "react";

/* ---------------------------------------------------------------------------
   The film.
   ----------------------------------------------------------------------------
   Two copies of the same file: the clip's last frame does not match its first,
   so a plain `loop` snaps a continent sideways every ten seconds. They
   ping-pong instead (see the cross-fade effect below), and the browser only
   fetches the asset once.

   It is a component rather than markup because both public documents need it:
   the landing hero, where it is the page, and the About hero, where it is the
   atmosphere behind the headline. The caller owns the frame (`.ds-bg` is
   positioned by whichever section hosts it) and the veil over it.
   ------------------------------------------------------------------------- */
const VIDEO_SRC =
  "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260912_104036_bd6924f6-3c8e-417e-8465-6d03c8c2e9e6.mp4";
const POSTER_SRC =
  "https://d2ol7oe51mr4n9.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/82e7eb75-c65f-490a-99b5-f3d1cad54200.webp";

/** The two copies take turns; this is the class the swap toggles. */
const ACTIVE = "ds-is-active";

export function LandingFilm({
  className,
  ariaLabel = "A stylised globe of Earth rendered as a green dot matrix against a starfield, slowly rotating",
}: {
  className?: string;
  ariaLabel?: string;
}) {
  const videoARef = useRef<HTMLVideoElement>(null);
  const videoBRef = useRef<HTMLVideoElement>(null);

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

  return (
    <div className={className ? `ds-bg ${className}` : "ds-bg"} role="img" aria-label={ariaLabel}>
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
  );
}
