import { describe, expect, it } from "vitest";
import {
  BRD_REFRESH_MS, BRD_STATES, EVIDENCE_WORDS, approvedCount, brdState, evidenceWords, hintWords, markdownUrl, mayDecide, mayGenerate, nameOf, namesOf, priorityTone,
  progressText, rejectReady, shortHash,
} from "@/lib/brd";

describe("brief words", () => {
  it("has plain words and colours for every state, and passes unknown ones through", () => {
    expect(Object.keys(BRD_STATES).sort()).toEqual(["APPROVED", "DRAFT", "PENDING_APPROVAL", "SUPERSEDED"]);
    expect(brdState("PENDING_APPROVAL")).toMatchObject({ label: "Waiting for the sponsors", tone: "amber" });
    expect(brdState("APPROVED")).toMatchObject({ label: "Approved and locked", tone: "green" });
    expect(brdState("SUPERSEDED").tone).toBe("grey");
    expect(brdState("DRAFT").tone).toBe("grey");
    expect(brdState("ODD")).toEqual({ label: "ODD", tone: "grey", hint: "" });
    expect(BRD_REFRESH_MS).toBe(10000);
  });

  it("colours priorities", () => {
    expect([priorityTone("MUST"), priorityTone("SHOULD"), priorityTone("COULD"), priorityTone("X")]).toEqual(["red", "amber", "grey", "grey"]);
  });

  it("says what proof is needed and what the platform can check itself", () => {
    expect(Object.keys(EVIDENCE_WORDS)).toHaveLength(5);
    expect(evidenceWords(["LIVE_URL_CHECK", "SCREENSHOT"])).toBe("a check of the live page, a screenshot");
    expect(evidenceWords(["ODD"])).toBe("ODD");
    expect(evidenceWords([])).toBe("");
    expect(hintWords(null)).toBeNull();
    expect(hintWords({ type: "URL_REACHABLE", path: "/stay", text: null })).toBe("The page /stay opens");
    expect(hintWords({ type: "PAGE_CONTAINS", path: "/menu", text: "Fish" })).toBe("The page /menu contains “Fish”");
    expect(hintWords({ type: "FILE_EXISTS", path: "/robots.txt", text: null })).toBe("The file /robots.txt exists");
    expect(hintWords({ type: "MOBILE_VIEWPORT", path: null, text: null })).toBe("The page works on a phone screen");
    expect(hintWords({ type: "NEW", path: null, text: null })).toBe("NEW");
  });

  it("shortens fingerprints and names people", () => {
    expect(shortHash("abcdef1234567890")).toBe("abcdef123456");
    expect(shortHash("abc")).toBe("abc");
    expect(shortHash("abcdef", 3)).toBe("abc");
    const names = { 1: "Lakshmi", 2: "Ravi" };
    expect(nameOf(names, 1)).toBe("Lakshmi");
    expect(nameOf(names, 9)).toBe("someone");
    expect(nameOf(names, null)).toBe("nobody yet");
    expect(namesOf(names, [1, 2])).toBe("Lakshmi, Ravi");
    expect(namesOf(names, [])).toBe("nobody yet");
    expect(namesOf(names, [2, 9])).toBe("Ravi, someone");
  });

  it("counts approvals and words the progress", () => {
    expect(progressText(1, 3)).toBe("1 of 3 sponsors approved");
    expect(progressText(1, 1)).toBe("1 of 1 sponsor approved");
    expect(progressText(0, 2)).toBe("0 of 2 sponsors approved");
    const a = (decision: string) => ({ member_id: 1, member_name: "x", decision, comment: null, created_at: "x" });
    expect(approvedCount([a("APPROVE"), a("REJECT"), a("APPROVE")])).toBe(2);
    expect(approvedCount([])).toBe(0);
  });

  it("lets only the lead and sponsors decide, on the open version, during review", () => {
    expect([["LEAD", "PENDING_APPROVAL", "BRD_REVIEW"], ["SPONSOR", "PENDING_APPROVAL", "BRD_REVIEW"]].map(([r, b, p]) => mayDecide(r, b, p))).toEqual([true, true]);
    expect([["SUPPORTER", "PENDING_APPROVAL", "BRD_REVIEW"], ["FREELANCER", "PENDING_APPROVAL", "BRD_REVIEW"], [null, "PENDING_APPROVAL", "BRD_REVIEW"],
            ["LEAD", "APPROVED", "BRD_REVIEW"], ["LEAD", "SUPERSEDED", "BRD_REVIEW"], ["LEAD", "DRAFT", "BRD_REVIEW"], ["LEAD", "PENDING_APPROVAL", "REQUIREMENTS"], ["LEAD", "PENDING_APPROVAL", "CONTRACTING"]]
      .map(([r, b, p]) => mayDecide(r, b as string, p as string))).toEqual([false, false, false, false, false, false, false, false]);
  });

  it("lets only the lead write the brief, and only while gathering requirements", () => {
    expect([mayGenerate("LEAD", "REQUIREMENTS"), mayGenerate("SPONSOR", "REQUIREMENTS"), mayGenerate(null, "REQUIREMENTS"), mayGenerate("LEAD", "BRD_REVIEW"), mayGenerate("LEAD", "")]).toEqual([true, false, false, false, false]);
  });

  it("needs a comment to ask for changes, not just spaces", () => {
    expect([rejectReady("Change the menu"), rejectReady(""), rejectReady("  \n "), rejectReady(" x ")]).toEqual([true, false, false, true]);
  });

  it("builds the download address", () => {
    expect(markdownUrl("http://api.test/api", 7, 3)).toBe("http://api.test/api/projects/7/brd/3.md");
  });
});
