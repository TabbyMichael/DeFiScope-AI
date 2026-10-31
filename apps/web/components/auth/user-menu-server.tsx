import Link from "next/link";

import { UserMenu } from "@/components/auth/user-menu";
import { ANONYMOUS_SUBJECT, canSwitchRole, getSession } from "@/lib/auth";

/**
 * Server wrapper: the only place that reads the session for the header.
 *
 * Must be rendered inside a `<Suspense>` boundary — it touches `cookies()`, and
 * with `cacheComponents` on, that is what lets the rest of the shell stream.
 */
export async function UserMenuServer() {
  const session = await getSession();
  const subject = session?.subject ?? ANONYMOUS_SUBJECT;
  return <UserMenu subject={subject} demo={canSwitchRole(session)} />;
}

/** Footer slot for the sidebar: who you are, or a way in. */
export async function SidebarAuthFooter() {
  const session = await getSession();
  const subject = session?.subject;

  if (!subject?.authenticated) {
    return (
      <div className="px-2 py-1 text-xs leading-relaxed text-muted-foreground group-data-[collapsible=icon]:hidden">
        <Link href="/login" className="font-medium underline hover:text-foreground">
          Sign in
        </Link>{" "}
        to see scoped data.
      </div>
    );
  }

  return (
    <div className="px-2 py-1 text-xs leading-relaxed text-muted-foreground group-data-[collapsible=icon]:hidden">
      <span className="block truncate font-medium text-foreground">{subject.email}</span>
      <span className="block truncate">
        {subject.role.replace("_", " ")} · clearance {subject.clearance}
      </span>
    </div>
  );
}
