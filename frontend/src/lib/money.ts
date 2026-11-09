/** The one money formatter (SPEC 11.2): integer cents in, "$1,234.50" out. Floats are refused, never shown. */
export function formatMoney(cents: number, currency = "USD"): string {
  if (!Number.isSafeInteger(cents)) {
    throw new TypeError(`money must be whole cents, got ${String(cents)}`);
  }
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const dollars = Math.trunc(abs / 100).toLocaleString("en-US");
  const rest = String(abs % 100).padStart(2, "0");
  const symbol = currency === "USD" ? "$" : `${currency} `;
  return `${sign}${symbol}${dollars}.${rest}`;
}

/** Share of a goal as a whole percent, never above 100 and never below 0 (used for progress bars). */
export function percentOf(part: number, whole: number): number {
  if (!Number.isFinite(part) || !Number.isFinite(whole) || whole <= 0) return 0;
  return Math.max(0, Math.min(100, Math.floor((part * 100) / whole)));
}
