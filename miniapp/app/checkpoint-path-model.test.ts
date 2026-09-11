import { describe, expect, it } from "vitest";

import { checkpointBlockLabel, checkpointNodeCaption, checkpointNodeMarker, checkpointReopenLabel } from "./checkpoint-path-model";
import type { CheckpointNode } from "./types";

function node(overrides: Partial<CheckpointNode> = {}): CheckpointNode {
  return {
    unit_index: 0,
    topic_from: 0,
    topic_to: 2,
    topics: ["A", "B", "C"],
    status: "available",
    available_at: null,
    passed_at: null,
    mastered_count: null,
    question_total: null,
    ...overrides,
  };
}

describe("checkpoint path model", () => {
  it("labels a block by its first and last topic when it spans more than two", () => {
    expect(checkpointBlockLabel(node({ topics: ["A", "B", "C"] }))).toBe("A — C");
    expect(checkpointBlockLabel(node({ topics: ["A", "B"] }))).toBe("A, B");
    expect(checkpointBlockLabel(node({ topics: [] }))).toBe("Блок 1");
  });

  it("captions each status without leaking an accuracy percent", () => {
    expect(checkpointNodeCaption(node({ status: "available", topics: ["A", "B", "C"] }))).toContain("A — C");
    expect(checkpointNodeCaption(node({ status: "locked" }))).toContain("Откроется");
    expect(checkpointNodeCaption(node({ status: "cooldown", available_at: "2026-09-20T00:00:00Z" }))).toContain("откроется");
    expect(checkpointNodeCaption(node({ status: "passed", mastered_count: 3, question_total: 5 }))).toBe("Пройден · 3/5");
    expect(checkpointNodeCaption(node({ status: "passed", mastered_count: null, question_total: null }))).toBe("Пройден");
  });

  it("gives a marker per status", () => {
    expect(checkpointNodeMarker("passed")).toBe("✓");
    expect(checkpointNodeMarker("locked")).toBe("🔒");
    expect(checkpointNodeMarker("available")).toBe("◆");
    expect(checkpointNodeMarker("cooldown")).toBe("◆");
  });

  it("formats a reopen day and tolerates a missing instant", () => {
    expect(checkpointReopenLabel("2026-09-20T00:00:00Z")).toMatch(/\d/);
    expect(checkpointReopenLabel(null)).toBe("");
    expect(checkpointReopenLabel("not-a-date")).toBe("");
  });
});
