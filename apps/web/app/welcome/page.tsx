import { DeFiScopeLanding } from "@/components/landing/defiscope-landing";

/**
 * The landing shell is static; only its live coverage band reads the backend.
 *
 * That split is what `cacheComponents` wants: the hero, the chrome and every
 * explanatory section prerender to static HTML, while the one data-shaped region
 * (the numbers at `/api/status`) streams under a `Suspense` boundary inside
 * `DeFiScopeLanding`. A cold or unreachable API can therefore never blank the
 * page or fail the build: the suspended band simply renders its honest `n/a`.
 */
export default function WelcomePage() {
  return <DeFiScopeLanding />;
}
