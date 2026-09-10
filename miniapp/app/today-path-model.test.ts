import { describe, expect, it } from "vitest";

import {
  estimatedMinutesLabel,
  pathPreview,
  todayCtaSummary,
  topicMasteryPercent,
  topicNodeCaption,
} from "./today-path-model";
import type { TodaySession, TopicPathNode } from "./types";

function node(overrides: Partial<TopicPathNode> & Pick<TopicPathNode, "topic" | "index" | "status">): TopicPathNode {
  return { total: 10, mastered: 0, done_at: null, ...overrides };
}

const path: TopicPathNode[] = [
  node({ topic: "A", index: 0, status: "done", mastered: 10, total: 10 }),
  node({ topic: "B", index: 1, status: "done", mastered: 8, total: 8 }),
  node({ topic: "C", index: 2, status: "current", mastered: 7, total: 12 }),
  node({ topic: "D", index: 3, status: "locked" }),
  node({ topic: "E", index: 4, status: "locked" }),
];

describe("topicMasteryPercent", () => {
  it("rounds the mastered share to a whole percent", () => {
    expect(topicMasteryPercent(7, 12)).toBe(58);
    expect(topicMasteryPercent(0, 0)).toBe(0);
  });
  it("never exceeds 100 when mastered runs past total", () => {
    expect(topicMasteryPercent(13, 12)).toBe(100);
  });
});

describe("pathPreview", () => {
  it("centres on the current topic with its neighbours", () => {
    expect(pathPreview(path).map((item) => item.topic)).toEqual(["B", "C", "D"]);
  });
  it("returns the whole path when short", () => {
    expect(pathPreview(path.slice(0, 2)).map((item) => item.topic)).toEqual(["A", "B"]);
  });
  it("falls back to the first nodes when nothing is current", () => {
    const done = path.map((item) => ({ ...item, status: "done" as const }));
    expect(pathPreview(done).map((item) => item.topic)).toEqual(["A", "B", "C"]);
  });
});

describe("topicNodeCaption", () => {
  it("labels each status distinctly", () => {
    expect(topicNodeCaption(path[0])).toContain("Тема пройдена");
    expect(topicNodeCaption(path[2])).toContain("Сейчас здесь");
    expect(topicNodeCaption(path[3])).toContain("Откроется");
  });
});

describe("todayCtaSummary + estimatedMinutesLabel", () => {
  const today = {
    size: 5,
    topic: "Тепловые явления",
    estimated_minutes: 4,
  } as TodaySession;
  it("pluralises the задания count and keeps the topic", () => {
    expect(todayCtaSummary(today)).toEqual({ size: "5 заданий", topic: "Тепловые явления" });
  });
  it("labels the estimate with a floor of one minute", () => {
    expect(estimatedMinutesLabel(4)).toBe("~4 мин");
    expect(estimatedMinutesLabel(0)).toBe("~1 мин");
  });
});
