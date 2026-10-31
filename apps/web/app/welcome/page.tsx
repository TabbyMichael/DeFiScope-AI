import { DeFiScopeLanding } from "@/components/landing/defiscope-landing";

/**
 * The marketing page is fully static — no cookies, no API reads — so it needs no
 * Suspense boundary and can be prerendered at build time. `cacheComponents` is
 * happy with it for exactly that reason.
 */
export default function WelcomePage() {
  return <DeFiScopeLanding />;
}
