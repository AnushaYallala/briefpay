/** Dates are shown in UTC with the label, so the same moment reads the same for everyone (and in tests). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "none";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "unknown";
  const text = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }).format(d);
  return `${text} UTC`;
}
