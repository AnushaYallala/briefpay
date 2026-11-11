import { describe, expect, it } from "vitest";
import {
  BOARD_STATUS, CAMPAIGN_REFRESH_MS, CLOCK_MS, CLOSE_POLICY_WORDS, MONEY_NOTES, boardRows, centsToDollars, countdownText, deadlineProblem, deadlineToIso, dollarsToCents,
  isLive, isoToLocalInput, mayLaunch, moneyNote, nudgeLabel, percentWords, whatsappUrl,
} from "@/lib/campaign";
import { parseApiDate } from "@/lib/time";
import { campaignView, leadPart, ledgerRow } from "./helpers";

const T0 = Date.parse("2026-11-10T10:00:00Z");
const left = (seconds: number) => countdownText("2026-11-10T10:00:00Z", T0 - seconds * 1000, parseApiDate);

describe("words", () => {
  it("has words for every campaign state and both closing policies", () => {
    expect(Object.keys(MONEY_NOTES).sort()).toEqual(["CANCELLED", "CAPTURED", "CAPTURING", "FAILED", "FAILING", "OPEN", "SETUP"]);
    expect(moneyNote("OPEN")).toContain("Nothing is charged unless the goal is reached");
    expect(moneyNote("FAILED")).toContain("nobody was charged");
    expect(moneyNote("CAPTURED")).toContain("collected");
    expect(moneyNote("NOPE")).toBe("");
    expect(Object.keys(CLOSE_POLICY_WORDS).sort()).toEqual(["AT_DEADLINE", "EARLY_ON_GOAL"]);
    expect([CAMPAIGN_REFRESH_MS, CLOCK_MS]).toEqual([10000, 30000]);
  });

  it("says what the Strategist's numbers and drafts are", () => {
    expect([percentWords(0.0256), percentWords(0.5), percentWords(1), percentWords(0.004)]).toEqual(["3%", "50%", "100%", "0%"]);
    expect(whatsappUrl("Hi there & you?")).toBe("https://wa.me/?text=Hi%20there%20%26%20you%3F");
    expect(nudgeLabel({ source: "TEMPLATE" })).toBe("Draft from a template");
    expect(nudgeLabel({ source: "AI" })).toBe("Draft written by the AI, checked by the system");
  });

  it("knows which states are still live and who may open a campaign", () => {
    expect(["SETUP", "OPEN"].map(isLive)).toEqual([true, true]);
    expect(["CAPTURING", "CAPTURED", "FAILING", "FAILED", "CANCELLED"].map(isLive)).toEqual([false, false, false, false, false]);
    const lead = (can: boolean | undefined, state = "SETUP") => campaignView({ state, lead: can === undefined ? undefined : leadPart({ can_launch: can }) });
    expect([mayLaunch(lead(true)), mayLaunch(lead(false)), mayLaunch(lead(undefined)), mayLaunch(lead(true, "OPEN"))]).toEqual([true, false, false, false]);
  });
});

describe("countdown", () => {
  it("shows the two largest units, singular and plural, and says closed once it has passed", () => {
    expect([left(-5), left(0), left(30), left(59)]).toEqual(["Closed", "Closed", "Less than a minute left", "Less than a minute left"]);
    expect(left(59.6)).toBe("Less than a minute left");                       // seconds are cut, not rounded
    expect(left(86300)).toBe("23 hours 58 minutes left");                         // just under a day is not a day
    expect(left(60)).toBe("1 minute left");
    expect(left(150)).toBe("2 minutes left");
    expect(left(3600)).toBe("1 hour 0 minutes left");
    expect(left(3600 + 120)).toBe("1 hour 2 minutes left");
    expect(left(2 * 3600 + 60)).toBe("2 hours 1 minute left");
    expect(left(86400)).toBe("1 day 0 hours left");
    expect(left(86400 + 3600)).toBe("1 day 1 hour left");
    expect(left(2 * 86400 + 5 * 3600 + 59 * 60)).toBe("2 days 5 hours left");
  });
});

describe("the pledge board", () => {
  const opens = "2026-11-10T10:00:00+00:00";
  const row = (seq: number, type: string, ref: string | null, when: string, name: string | null, cents = 0) =>
    ledgerRow({ seq, type, ref_type: "pledge", ref_id: ref, counterparty: name, created_at: when, amount_cents: cents });

  it("shows one row per pledge with its latest step, the amount only once collected, newest first", () => {
    const rows = [
      row(1, "PLEDGE_AUTHORIZED", "4", "2026-11-10T11:00:00", "Lakshmi"), row(2, "PLEDGE_AUTHORIZED", "5", "2026-11-10T12:00:00", "Ravi"),
      row(3, "PLEDGE_AUTHORIZED", "6", "2026-11-10T13:00:00", "Meena"), row(4, "PLEDGE_CAPTURED", "4", "2026-11-11T09:00:00", "Lakshmi", 15000),
      row(5, "PLEDGE_VOIDED", "5", "2026-11-11T09:30:00", "Ravi"),
    ];
    const b = boardRows(rows, opens, parseApiDate);
    expect(b.map((r) => [r.pledge, r.name, r.status, r.amount_cents])).toEqual([["5", "Ravi", "VOIDED", null], ["4", "Lakshmi", "CAPTURED", 15000], ["6", "Meena", "AUTHORIZED", null]]);
  });

  it("keeps the amount known earlier, and falls back to a name when none is recorded", () => {
    const rows = [row(1, "PLEDGE_CAPTURED", "9", "2026-11-10T11:00:00", null, 5000), row(2, "PLEDGE_EXPIRED", "9", "2026-11-10T12:00:00", null)];
    expect(boardRows(rows, opens, parseApiDate)).toEqual([{ pledge: "9", name: "A supporter", status: "EXPIRED", amount_cents: 5000, at: "2026-11-10T12:00:00" }]);
    const named = [row(1, "PLEDGE_AUTHORIZED", "9", "2026-11-10T11:00:00", "Asha"), row(2, "PLEDGE_VOIDED", "9", "2026-11-10T12:00:00", null)];
    expect(boardRows(named, opens, parseApiDate)[0].name).toBe("Asha");
    const renamed = [row(1, "PLEDGE_AUTHORIZED", "9", "2026-11-10T11:00:00", "Old name"), row(2, "PLEDGE_VOIDED", "9", "2026-11-10T12:00:00", "New name")];
    expect(boardRows(renamed, opens, parseApiDate)[0].name).toBe("New name");
  });

  it("ignores other ledger rows, rows before the campaign opened, pledges without a number, and every row when it has not opened", () => {
    const rows = [
      row(1, "PLEDGE_AUTHORIZED", "1", "2026-11-09T09:00:00", "Earlier round"), row(2, "PLEDGE_AUTHORIZED", null, "2026-11-10T11:00:00", "No id"),
      ledgerRow({ seq: 3, type: "STATE_CHANGE", ref_type: "project", ref_id: "1", created_at: "2026-11-10T11:00:00" }),
      ledgerRow({ seq: 4, type: "PLEDGE_AUTHORIZED", ref_type: "project", ref_id: "7", created_at: "2026-11-10T11:00:00", counterparty: "Wrong kind" }),
      row(5, "PLEDGE_AUTHORIZED", "2", "2026-11-10T10:00:00", "Exactly at opening"), row(6, "REFUND", "2", "2026-11-10T14:00:00", "Not a pledge step"),
    ];
    expect(boardRows(rows, opens, parseApiDate).map((r) => r.name)).toEqual(["Exactly at opening"]);
    expect(boardRows(rows, null, parseApiDate)).toEqual([]);
    expect(boardRows([], opens, parseApiDate)).toEqual([]);
  });

  it("breaks a tie in time by pledge number, newest first", () => {
    const rows = [row(1, "PLEDGE_AUTHORIZED", "3", "2026-11-10T11:00:00", "A"), row(2, "PLEDGE_AUTHORIZED", "12", "2026-11-10T11:00:00", "B")];
    expect(boardRows(rows, opens, parseApiDate).map((r) => r.pledge)).toEqual(["12", "3"]);
  });

  it("colours each status", () => {
    expect(Object.fromEntries(Object.entries(BOARD_STATUS).map(([k, v]) => [k, `${v.label}:${v.tone}`]))).toEqual({ AUTHORIZED: "Held:teal", CAPTURED: "Collected:green", VOIDED: "Released:grey", EXPIRED: "Expired:amber" });
  });
});

describe("typed values", () => {
  it("turns a typed deadline into a UTC moment and back", () => {
    expect(deadlineToIso("2026-11-12T14:30")).toBe("2026-11-12T14:30:00.000Z");
    for (const bad of ["", "2026-11-12", "2026-11-12T14:30:00", "12/11/2026 14:30", "2026-13-40T99:99"]) expect(deadlineToIso(bad), bad).toBeNull();
    expect(isoToLocalInput("2026-11-12T14:30:45+00:00", parseApiDate)).toBe("2026-11-12T14:30");
    expect(isoToLocalInput("2026-11-12T14:30:45", parseApiDate)).toBe("2026-11-12T14:30");
    expect(isoToLocalInput("2026-11-12T20:00:00+05:30", parseApiDate)).toBe("2026-11-12T14:30");
  });

  it("turns typed dollars into cents, blank into not set, and refuses the rest", () => {
    expect([dollarsToCents("5"), dollarsToCents("12.50"), dollarsToCents(" 0.05 "), dollarsToCents("0"), dollarsToCents("1234.5")]).toEqual([500, 1250, 5, 0, 123450]);
    expect([dollarsToCents("0.29"), dollarsToCents("1.15"), dollarsToCents("4.35")]).toEqual([29, 115, 435]);   // no lost cents from floating point
    expect([dollarsToCents(""), dollarsToCents("   ")]).toEqual([null, null]);
    for (const bad of ["-5", "5.123", "abc", "1e3", "$5", "5,00", "1234567", ".5"]) expect(dollarsToCents(bad), bad).toBe("bad");
    expect([centsToDollars(500), centsToDollars(1250), centsToDollars(0), centsToDollars(null)]).toEqual(["5.00", "12.50", "0.00", ""]);
  });

  it("checks a typed deadline against the window, and says which side it is on", () => {
    const early = "2026-11-10T11:00:00+00:00";
    const late = "2026-11-13T08:00:00+00:00";
    const check = (s: string) => deadlineProblem(s, early, late, parseApiDate);
    expect(check("2026-11-12T10:00")).toBeNull();
    expect(check("2026-11-10T11:00")).toBeNull();
    expect(check("2026-11-13T08:00")).toBeNull();
    expect(check("2026-11-10T10:59")).toContain("too soon");
    expect(check("2026-11-13T08:01")).toContain("too late");
    expect(check("")).toBe("Choose a date and time for the deadline.");
  });
});
