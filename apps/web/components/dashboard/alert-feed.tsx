import AlertItem from "@/components/dashboard/alert-item";
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
          <AlertItem key={a.id} alert={a} showTime={false} showCta={false} />
        ))}
      </CardContent>
    </Card>
  );
}
