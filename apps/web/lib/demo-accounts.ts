/**
 * The four seeded demo accounts, mirrored from `services/api/app/security/seed.py`.
 *
 * Kept in one module so the login page's one-click buttons and the header role
 * switcher cannot drift apart. Each account changes exactly one axis from the
 * one above it, which is what makes the policy layer observable rather than
 * merely describable:
 *
 *  - viewer  : read-only, clearance 1, sees everything
 *  - analyst : same clearance, but scoped to Lending + Dexes
 *  - officer : clearance 2, so critical alerts stop being withheld
 *  - admin   : clearance 3 and bypasses every gate
 */
export const DEMO_ACCOUNTS = [
  { email: "viewer@demo", label: "Viewer", hint: "read-only · clearance 1" },
  { email: "analyst@demo", label: "Analyst", hint: "Lending + Dexes only" },
  { email: "officer@demo", label: "Risk officer", hint: "sees critical alerts" },
  { email: "admin@demo", label: "Admin", hint: "bypasses every gate" },
] as const;

export type DemoAccount = (typeof DEMO_ACCOUNTS)[number];
