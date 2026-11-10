import { describe, expect, it } from "vitest";
import {
  BA_REFRESH_MS, JOB_POLL_MS, QUESTION_STATES, SESSION_STATES, addressedText, canUpload, groupQuestions, parseRef, percent, points, questionState, refLines, refWords,
  sessionState, sparkPoints, sparkY,
} from "@/lib/ba";
import { baQuestion } from "./helpers";

describe("references", () => {
  it("reads line references and ignores everything else", () => {
    expect(parseRef("L3")).toEqual({ from: 3, to: 3 });
    expect(parseRef("L3-L5")).toEqual({ from: 3, to: 5 });
    expect(parseRef(" L12-L12 ")).toEqual({ from: 12, to: 12 });
    for (const bad of ["answer:12", "L0", "L5-L3", "3", "l3", "L3-5", "", "L-1"]) expect(parseRef(bad), bad).toBeNull();
  });

  it("lists every line a set of references names", () => {
    expect([...refLines(["L3-L5", "L9", "answer:2", "junk"])].sort((a, b) => a - b)).toEqual([3, 4, 5, 9]);
    expect(refLines([]).size).toBe(0);
    expect(refLines(["L1-L999999"]).size).toBe(5000);                   // a wild range cannot freeze the page
  });

  it("says where a reference points in words", () => {
    expect(refWords("L3")).toBe("line 3");
    expect(refWords("L3-L5")).toBe("lines 3 to 5");
    expect(refWords("L4-L4")).toBe("line 4");
    expect(refWords("answer:12")).toBe("answer 12");
    expect(refWords("weird")).toBe("weird");
  });
});

describe("words and numbers", () => {
  it("has plain words for every session and question state", () => {
    expect(Object.keys(SESSION_STATES).sort()).toEqual(["ACTIVE", "BRD_GENERATED", "FINALIZED", "MAX_ROUNDS", "READY"]);
    expect(Object.keys(QUESTION_STATES).sort()).toEqual(["ANSWERED", "OPEN", "SKIPPED"]);
    expect(sessionState("READY")).toMatchObject({ label: "Ready for the brief", tone: "green" });
    expect(sessionState("ACTIVE").tone).toBe("blue");
    expect(sessionState("MAX_ROUNDS").tone).toBe("amber");
    expect(sessionState("WEIRD")).toEqual({ label: "WEIRD", tone: "grey", hint: "" });
    expect(questionState("OPEN")).toEqual({ label: "Waiting for an answer", tone: "amber" });
    expect(questionState("ANSWERED").tone).toBe("green");
    expect(questionState("SKIPPED").tone).toBe("grey");
    expect(questionState("ODD")).toEqual({ label: "ODD", tone: "grey" });
  });

  it("works out marks, percentages and the upload rule", () => {
    expect(points({ weight: 12, coverage_effective: 0.5 })).toBe(6);
    expect(points({ weight: 15, coverage_effective: 0.75 })).toBe(11.3);
    expect(points({ weight: 8, coverage_effective: 0 })).toBe(0);
    expect(percent(0.5)).toBe(50);
    expect(percent(0.666)).toBe(67);
    expect(percent(-1)).toBe(0);
    expect(percent(2)).toBe(100);
    expect(canUpload("hello")).toBe(true);
    expect(canUpload("  \n ")).toBe(false);
    expect(canUpload("")).toBe(false);
    expect(BA_REFRESH_MS).toBe(8000);
    expect(JOB_POLL_MS).toBe(2000);
  });

  it("says who a question is for", () => {
    const names = { 1: "Lakshmi", 2: "Ravi" };
    expect(addressedText(["ALL"], names)).toBe("Anyone on the sponsor side");
    expect(addressedText([1], names)).toBe("Lakshmi");
    expect(addressedText([1, 2], names)).toBe("Lakshmi and Ravi");
    expect(addressedText([1, 9], names)).toBe("Lakshmi and someone");
    expect(addressedText(["ODD"], names)).toBe("someone");
    expect(addressedText([2, "ALL"], names)).toBe("Anyone on the sponsor side");
  });
});

describe("questions and the score chart", () => {
  it("groups questions by round, newest round first, open questions first", () => {
    const qs = [baQuestion({ id: 1, round: 0, status: "ANSWERED" }), baQuestion({ id: 2, round: 1, status: "ANSWERED" }), baQuestion({ id: 3, round: 1, status: "OPEN" }), baQuestion({ id: 4, round: 0, status: "OPEN" }), baQuestion({ id: 5, round: 1, status: "OPEN" })];
    const g = groupQuestions(qs);
    expect(g.map((x) => x.round)).toEqual([1, 0]);
    expect(g[0].questions.map((q) => q.id)).toEqual([3, 5, 2]);
    expect(g[1].questions.map((q) => q.id)).toEqual([4, 1]);
    expect(groupQuestions([])).toEqual([]);
  });

  it("draws the score history as points, 0 at the bottom and 100 at the top", () => {
    expect(sparkPoints([], 240, 60)).toBe("");
    expect(sparkPoints([{ total: 50 }], 240, 60)).toBe("0,30");
    expect(sparkPoints([{ total: 0 }, { total: 100 }], 240, 60)).toBe("0,60 240,0");
    expect(sparkPoints([{ total: 58 }, { total: 79 }, { total: 93 }], 240, 60)).toBe("0,25.2 120,12.6 240,4.2");
    expect(sparkPoints([{ total: -10 }, { total: 500 }], 100, 100)).toBe("0,100 100,0");
    expect(sparkY(90, 60)).toBe(6);
    expect(sparkY(0, 60)).toBe(60);
    expect(sparkY(150, 60)).toBe(0);
  });
});
