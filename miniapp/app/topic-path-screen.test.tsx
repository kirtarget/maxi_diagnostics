import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { TopicPathScreen } from "./topic-path-screen";
import type { TopicPathNode, TopicPathResponse } from "./types";

function pathNode(topic: string, index: number, status: TopicPathNode["status"], mastered = 0, total = 10): TopicPathNode {
  return { topic, index, total, mastered, status, done_at: null };
}

const response: TopicPathResponse = {
  diagnostic_id: "phys",
  content_version: "v1",
  subject: "Физика",
  exam: "ОГЭ",
  current_topic: "Тепловые явления",
  done_count: 2,
  total_count: 5,
  topics: [
    pathNode("Физические величины", 0, "done", 8, 8),
    pathNode("Механические явления", 1, "done", 12, 12),
    pathNode("Тепловые явления", 2, "current", 7, 12),
    pathNode("Электромагнитные явления", 3, "locked"),
    pathNode("Квантовые явления", 4, "locked"),
  ],
  checkpoints: [],
};

describe("TopicPathScreen", () => {
  it("renders each topic with its status", () => {
    const html = renderToStaticMarkup(<TopicPathScreen path={response} />);
    expect(html).toContain("path-node is-done");
    expect(html).toContain("path-node is-current");
    expect(html).toContain("path-node is-locked");
    expect(html).toContain("Пройдено · 8/8");
    expect(html).toContain("Сейчас здесь · 7/12");
    expect(html).toContain("Пройдено 2 из 5");
  });

  it("draws the current topic progress bar", () => {
    const html = renderToStaticMarkup(<TopicPathScreen path={response} />);
    expect(html).toContain("path-node-progress");
    expect(html).toContain("aria-valuenow=\"58\"");
  });

  it("inserts a visual weekly checkpoint after the current topic without reusing the node status class", () => {
    const html = renderToStaticMarkup(<TopicPathScreen path={response} />);
    expect(html).toContain("path-checkpoint");
    expect(html).toContain("Чекпоинт недели");
    expect(html).toContain("Раз в неделю");
    // The checkpoint keeps its own class and never borrows a status modifier.
    expect(html).not.toContain("path-checkpoint is-done");
  });
});
