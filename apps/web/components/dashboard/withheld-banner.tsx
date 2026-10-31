import { EyeOff } from "lucide-react";

/**
 * "3 critical alerts withheld, clearance 2 required".
 *
 * The alternative, silently dropping the rows, would render an empty feed,
 * and an empty feed reads as *all clear*. Reporting the count while withholding
 * the content is the honest middle: you learn that something broke without
 * learning what, which is exactly what a clearance gate is for.
 */
export default function WithheldBanner({
  withheld,
  className,
}: {
  withheld: number;
  className?: string;
}) {
  if (withheld <= 0) return null;
  const noun = withheld === 1 ? "alert" : "alerts";
  return (
    <div
      className={
        "flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-800 dark:text-amber-200 " +
        (className ?? "")
      }
      role="status"
    >
      <EyeOff className="mt-0.5 size-3.5 shrink-0" />
      <p>
        <span className="font-semibold">
          {withheld} {noun} withheld
        </span>
        ; clearance 2 required. Your account can see that these fired, not what
        they say.
      </p>
    </div>
  );
}
