import { describe, expect, it } from "vitest";
import { MATCH_SYMBOL, REFRESH_MS, TYPE_LABELS, amountText, csvCell, csvSafe, filterRows, shortRef, toCsv, totalsRow, typeLabel, typesPresent } from "@/lib/ledger";
import { ledgerRow } from "./helpers";

const rows = [
  ledgerRow({ seq: 1, type: "STATE_CHANGE" }),
  ledgerRow({ seq: 2, type: "PLEDGE_CAPTURED", bucket: "POOL", amount_cents: 15000, running_balance_cents: 15000, counterparty: "Lakshmi", status: "Captured", paypal_ref: "CAPTURE-ABCDEFGHIJKLMNOP", actor_name: "PayPal" }),
  ledgerRow({ seq: 3, type: "PLEDGE_CAPTURED", bucket: "POOL", amount_cents: 10000, running_balance_cents: 25000, counterparty: "Ravi", status: "Captured", actor_name: "PayPal" }),
  ledgerRow({ seq: 4, type: "PAYOUT_SENT", bucket: "POOL", amount_cents: -25000, running_balance_cents: 0, counterparty: "Arjun", status: "Paid", actor_name: "PayPal" }),
];

describe("ledger words", () => {
  it("names every row type in plain words and falls back to the raw name", () => {
    expect(Object.keys(TYPE_LABELS)).toHaveLength(13);
    Object.entries(TYPE_LABELS).forEach(([k, v]) => { expect(v.length, k).toBeGreaterThan(5); expect(typeLabel(k)).toBe(v); });
    expect(typeLabel("SOMETHING_NEW")).toBe("SOMETHING_NEW");
    expect(typeLabel("PLEDGE_AUTHORIZED")).toBe("Pledge held");
  });
  it("refreshes every fifteen seconds", () => expect(REFRESH_MS).toBe(15000));
  it("has a symbol and a sentence for every PayPal answer", () => {
    expect(Object.keys(MATCH_SYMBOL).sort()).toEqual(["MATCH", "MISMATCH", "NOT_FOUND", "PENDING", "UNAVAILABLE"]);
    expect(MATCH_SYMBOL.MATCH.symbol).toBe("✓");
    expect(MATCH_SYMBOL.MISMATCH.symbol).toBe("✗");
    expect(MATCH_SYMBOL.NOT_FOUND.symbol).toBe("✗");
    expect(MATCH_SYMBOL.PENDING.symbol).toBe("⏳");
    Object.values(MATCH_SYMBOL).forEach((m) => expect(m.label.length).toBeGreaterThan(8));
  });
});

describe("filters and totals", () => {
  it("no chosen type shows everything; chosen types show only those", () => {
    expect(filterRows(rows, new Set())).toBe(rows);
    expect(filterRows(rows, new Set(["PLEDGE_CAPTURED"])).map((r) => r.seq)).toEqual([2, 3]);
    expect(filterRows(rows, new Set(["PLEDGE_CAPTURED", "PAYOUT_SENT"])).map((r) => r.seq)).toEqual([2, 3, 4]);
    expect(filterRows(rows, new Set(["NOPE"]))).toEqual([]);
  });
  it("lists the types in order of first appearance, once each", () => expect(typesPresent(rows)).toEqual(["STATE_CHANGE", "PLEDGE_CAPTURED", "PAYOUT_SENT"]));
  it("adds up the rows shown and keeps the ledger's own balance", () => {
    const t = totalsRow(filterRows(rows, new Set(["PLEDGE_CAPTURED"])), 0);
    expect([t.type, t.counterparty, t.amount_cents, t.running_balance_cents, t.seq]).toEqual(["TOTALS", "Total of 2 rows", 25000, 0, 0]);
    expect(totalsRow([rows[0]], 5).counterparty).toBe("Total of 1 row");
    expect(totalsRow([], 7)).toMatchObject({ counterparty: "Total of 0 rows", amount_cents: 0, running_balance_cents: 7 });
    expect(totalsRow(rows, 0).amount_cents).toBe(0);                                  // 15000 + 10000 - 25000
  });
});

describe("cell text", () => {
  it.each([[null, ""], ["", ""], ["short", "short"], ["0123456789", "0123456789"], ["01234567890", "01234567890"], ["012345678901", "0123456789…"], ["CAPTURE-ABCDEFGHIJKLMNOP", "CAPTURE-AB…"]])(
    "shortRef(%s) = %s", (ref, text) => expect(shortRef(ref)).toBe(text));
  it("shows a dash for a memo row and money otherwise", () => {
    expect(amountText(0)).toBe("–");
    expect(amountText(15000)).toBe("$150.00");
    expect(amountText(-25050)).toBe("-$250.50");
  });
});

describe("CSV export is safe to open in a spreadsheet", () => {
  it.each([
    ["=1+1", "'=1+1"], ["+SUM(A1)", "'+SUM(A1)"], ["-2+3", "'-2+3"], ["@SUM(A1)", "'@SUM(A1)"], ["=HYPERLINK(\"http://evil\")", "'=HYPERLINK(\"http://evil\")"],
    ["\tcmd", "'\tcmd"], ["\rcmd", "'\rcmd"], ["-", "'-"], ["+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"],
    ["-5.00", "-5.00"], ["15.00", "15.00"], ["+5", "+5"], ["Lakshmi", "Lakshmi"], ["a=b", "a=b"], ["", ""],
  ])("csvSafe(%j) = %j", (input, out) => expect(csvSafe(input)).toBe(out));
  it("treats nothing as empty text", () => { expect(csvSafe(null)).toBe(""); expect(csvSafe(undefined)).toBe(""); expect(csvSafe(0)).toBe("0"); });
  it("quotes cells with commas, quotes and line breaks, and still neutralises formulas", () => {
    expect(csvCell("a,b")).toBe('"a,b"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell("line1\nline2")).toBe('"line1\nline2"');
    expect(csvCell("=A1,B1")).toBe('"\'=A1,B1"');
    expect(csvCell("plain")).toBe("plain");
  });
  it("writes a header, one line per row with two-decimal amounts, and CRLF line ends", () => {
    const csv = toCsv(rows);
    const lines = csv.split("\r\n");
    expect(lines[0]).toBe("seq,time,bucket,type,counterparty,amount,pool_balance,status,paypal_ref,by");
    expect(lines[1]).toBe("1,2026-11-10T12:00:00,NONE,STATE_CHANGE,,0.00,0.00,,,BriefPay");
    expect(lines[2]).toBe("2,2026-11-10T12:00:00,POOL,PLEDGE_CAPTURED,Lakshmi,150.00,150.00,Captured,CAPTURE-ABCDEFGHIJKLMNOP,PayPal");
    expect(lines[4]).toBe("4,2026-11-10T12:00:00,POOL,PAYOUT_SENT,Arjun,-250.00,0.00,Paid,,PayPal");
    expect(lines.length).toBe(6);
    expect(csv.endsWith("\r\n") && !csv.includes("\n\n")).toBe(true);
  });
  it("neutralises a hostile name or reference in the file", () => {
    const csv = toCsv([ledgerRow({ counterparty: "=cmd|' /C calc'!A0", paypal_ref: "@evil", actor_name: "+1+1" })]);
    expect(csv).toContain(",'=cmd|' /C calc'!A0,");
    expect(csv).toContain(",'@evil,");
    expect(csv).toContain(",'+1+1\r\n");
  });
  it("an empty ledger exports only the header", () => expect(toCsv([])).toBe("seq,time,bucket,type,counterparty,amount,pool_balance,status,paypal_ref,by\r\n"));
});
