import { Suspense } from "react";

import { ChatPanel } from "@/components/chat/chat-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export const metadata = {
  title: "Ask the analyst · DeFiScope AI",
  description: "Grounded Q&A over DeFiScope's methodology and protocol evidence.",
};

// Server component: reads the tracked (monitored) protocol list via the
// server-only API URL (never exposed to the browser) and hands a lightweight
// name/slug list to the client chat panel. The scope list is the analyzed set,
// not the full discovery catalog. A failure here just means no protocol scope
// dropdown - the chat still works for general methodology questions.
async function AskContent() {
  let protocols: { slug: string; name: string }[] = [];
  try {
    const board = await api.dashboard();
    protocols = board.protocols
      .map((p) => ({ slug: p.slug, name: p.name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  } catch {
    protocols = []; // chat degrades to general questions; never blocks the page
  }
  return <ChatPanel protocols={protocols} />;
}

function AskSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

export default function AskPage() {
  return (
    <div className="mx-auto flex h-[calc(100vh-7rem)] w-full max-w-3xl flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Ask the analyst</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Grounded questions over the risk methodology and each protocol&apos;s captured evidence.
          Always cited, and honest about what the data can&apos;t establish.
        </p>
      </div>
      <Suspense fallback={<AskSkeleton />}>
        <AskContent />
      </Suspense>
    </div>
  );
}
