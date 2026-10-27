import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Alert } from "@/lib/types";

const SEVERITY_STYLE: Record<string, string> = {
  critical: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
  warning: "border-yellow-500/40 bg-yellow-500/10 text-yellow-800 dark:text-yellow-300",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

export default function AlertFeed({
  alerts,
  limit = 8,
}: {
  alerts: Alert[];
  limit?: number;
}) {
  const shown = alerts.slice(0, limit);

  return (
    <Card>
      <CardHeader>
        <CardDescription>Rules evaluated on the latest data window</CardDescription>
        <CardTitle>Alert feed</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {shown.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No rules triggered. Quiet is not the same as safe — rules only fire on
            TVL-observable signals.
          </p>
        )}
        {shown.map((a) => (
          <div
            key={a.id}
            className={`rounded-lg border p-2.5 text-sm ${SEVERITY_STYLE[a.severity] ?? SEVERITY_STYLE.info}`}
          >
            <div className="flex items-center justify-between gap-2">
              <Link
                href={`/protocols/${a.slug}`}
                className="font-medium hover:underline"
              >
                {a.protocol}
              </Link>
              <Badge variant="outline" className="text-[10px] uppercase">
                {a.rule}
              </Badge>
            </div>
            <p className="mt-1 text-xs leading-relaxed opacity-90">{a.message}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
