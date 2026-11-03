import { fetchCoverage } from "@/lib/api";

/**
 * Renders the live monitor cadence (e.g. "2 minutes") straight from /api/status,
 * so the copy on the alerts and about pages always matches the scheduler's
 * configured interval instead of a hardcoded number that can silently drift out
 * of sync with DEFISCOPE_MONITOR_INTERVAL_MINUTES.
 *
 * Must be used inside a <Suspense> boundary: it reads runtime data, and Next 16
 * Cache Components treats that as a dynamic region. When the backend is
 * unreachable it degrades to `fallback` (an honest "not measured") rather than
 * blocking the prerender or lying about a specific number.
 */
export default async function LiveCadence({
  fallback = "a few minutes",
}: {
  fallback?: string;
}) {
  const coverage = await fetchCoverage();
  const minutes = coverage?.monitor_interval_minutes;
  if (minutes == null) {
    return <>{fallback}</>;
  }
  return <>{`${minutes} minute${minutes === 1 ? "" : "s"}`}</>;
}
