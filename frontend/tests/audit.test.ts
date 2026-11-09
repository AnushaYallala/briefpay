import { describe, expect, it } from "vitest";
import { AGENT_LABELS, RUN_STATUS, agentLabel, agentsPresent, filterRuns, latencyText, shortHash, statusInfo, summarize } from "@/lib/audit";
import { run } from "./helpers";

describe("audit logic", () => {
  it("has plain words for agents and statuses, and passes unknown ones through", () => {
    expect(agentLabel("BRD_GEN")).toBe("Brief writer");
    expect(agentLabel("NEW_AGENT")).toBe("NEW_AGENT");
    expect(statusInfo("OK")).toEqual({ label: "Answered", tone: "green" });
    expect(statusInfo("ERROR").tone).toBe("red");
    expect(statusInfo("SCHEMA_INVALID").tone).toBe("red");
    expect(statusInfo("REPLAYED").tone).toBe("blue");
    expect(statusInfo("WEIRD")).toEqual({ label: "WEIRD", tone: "grey" });
    expect(Object.keys(AGENT_LABELS)).toHaveLength(7);
    expect(Object.keys(RUN_STATUS)).toHaveLength(4);
  });

  it("filters by agent and lists agents in order of first appearance", () => {
    const runs = [run({ id: 3, agent: "BA_SCORE" }), run({ id: 2, agent: "BRD_GEN" }), run({ id: 1, agent: "BA_SCORE" })];
    expect(filterRuns(runs, null)).toHaveLength(3);
    expect(filterRuns(runs, "BA_SCORE").map((r) => r.id)).toEqual([3, 1]);
    expect(filterRuns(runs, "NONE")).toEqual([]);
    expect(agentsPresent(runs)).toEqual(["BA_SCORE", "BRD_GEN"]);
  });

  it("summarises calls, failures, average time and tokens", () => {
    const runs = [
      run({ latency_ms: 100, input_tokens: 10, output_tokens: 5 }),
      run({ latency_ms: 300, status: "ERROR", input_tokens: null, output_tokens: null }),
      run({ latency_ms: 200, status: "SCHEMA_INVALID", input_tokens: 1, output_tokens: 1 }),
      run({ latency_ms: 0, status: "REPLAYED", input_tokens: 0, output_tokens: 0 }),
    ];
    expect(summarize(runs)).toEqual({ runs: 4, failed: 2, avgLatencyMs: 150, tokens: 17 });
    expect(summarize([run({ latency_ms: 1 }), run({ latency_ms: 2 })]).avgLatencyMs).toBe(2);       // 1.5 rounds up, not down
    expect(summarize([run({ latency_ms: 1 }), run({ latency_ms: 1 }), run({ latency_ms: 2 })]).avgLatencyMs).toBe(1);   // 1.33 rounds down
    expect(summarize([])).toEqual({ runs: 0, failed: 0, avgLatencyMs: 0, tokens: 0 });
  });

  it("shortens hashes and formats times taken", () => {
    expect(shortHash("abcdef1234567890")).toBe("abcdef12");
    expect(shortHash("abc")).toBe("abc");
    expect(shortHash("abcdefgh")).toBe("abcdefgh");
    expect(shortHash("abcdefghi", 4)).toBe("abcd");
    expect(latencyText(0)).toBe("0 ms");
    expect(latencyText(999)).toBe("999 ms");
    expect(latencyText(1000)).toBe("1.0 s");
    expect(latencyText(2540)).toBe("2.5 s");
  });
});
