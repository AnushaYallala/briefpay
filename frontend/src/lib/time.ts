/**
 * Dates are shown in UTC with the label, so the same moment reads the same for everyone (and in tests).
 * The API sends some timestamps WITHOUT an offset ("2026-11-10T12:00:00"); those are UTC by convention. A browser would read them as
 * local time, so a missing offset is read as UTC here.
 */
const HAS_ZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i;

export function parseApiDate(iso: string): Date {
  const text = iso.trim();
  const dateTime = /^\d{4}-\d{2}-\d{2}T/.test(text);
  return new Date(dateTime && !HAS_ZONE.test(text) ? `${text}Z` : text);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "none";
  const d = parseApiDate(iso);
  if (Number.isNaN(d.getTime())) return "unknown";
  const text = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" }).format(d);
  return `${text} UTC`;
}
