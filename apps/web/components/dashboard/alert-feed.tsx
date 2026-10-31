import AlertItem from "@/components/dashboard/alert-item";
import WithheldBanner from "@/components/dashboard/withheld-banner";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Alert } from "@/lib/types";

export default function AlertFeed({
  alerts,
  withheld = 0,
  limit = 8,
}: {
  alerts: Alert[];
  /** Rows the API withheld above the caller's clearance: counted, not shown. */
  withheld?: number;
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
        <WithheldBanner withheld={withheld} />
        {shown.length === 0 && (
          <p className="text-sm text-muted-foreground">
            No rules triggered. Quiet is not the same as safe. Rules only fire on
            TVL-observable signals.
          </p>
        )}
        {shown.map((a) => (
          <AlertItem key={a.id} alert={a} showTime={false} showCta={false} />
        ))}
      </CardContent>
    </Card>
  );
}
