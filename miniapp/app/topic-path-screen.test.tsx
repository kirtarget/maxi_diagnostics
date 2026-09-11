// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";
import { act } from "react";

import { TopicPathScreen } from "./topic-path-screen";
import type { CheckpointNode, TopicPathNode, TopicPathResponse } from "./types";

function pathNode(topic: string, index: number, status: TopicPathNode["status"], mastered = 0, total = 10): TopicPathNode {
  return { topic, index, total, mastered, status, done_at: null };
}

function checkpoint(overrides: Partial<CheckpointNode> = {}): CheckpointNode {
  return {
    unit_index: 0,
    topic_from: 0,
    topic_to: 2,
    topics: ["Физические величины", "Механические явления", "Тепловые явления"],
    status: "available",
    available_at: null,
    passed_at: null,
    mastered_count: null,
    question_total: null,
    ...overrides,
  };
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

  it("renders no checkpoint node when the path has none", () => {
    const html = renderToStaticMarkup(<TopicPathScreen path={response} />);
    expect(html).not.toContain("path-checkpoint");
  });

  it("renders an available checkpoint after its unit's last topic as a clickable button", () => {
    const withCheckpoint = { ...response, checkpoints: [checkpoint({ topic_to: 1, topics: ["Физические величины", "Механические явления"] })] };
    const html = renderToStaticMarkup(<TopicPathScreen path={withCheckpoint} onStartCheckpoint={vi.fn()} />);
    expect(html).toContain("path-checkpoint is-available");
    expect(html).toContain("path-checkpoint-button");
    expect(html).toContain("Чекпоинт недели");
    expect(html).toContain("Короткий срез закрывает блок");
    // The checkpoint keeps its own class and never borrows a topic status modifier.
    expect(html).not.toContain("path-checkpoint is-done");
    expect(html).not.toContain("path-node is-checkpoint");
  });

  it("shows locked, cooldown and passed checkpoints without a launch button", () => {
    const cooldown = { ...response, checkpoints: [checkpoint({ status: "cooldown", available_at: "2026-09-20T00:00:00Z" })] };
    const cooldownHtml = renderToStaticMarkup(<TopicPathScreen path={cooldown} onStartCheckpoint={vi.fn()} />);
    expect(cooldownHtml).toContain("path-checkpoint is-cooldown");
    expect(cooldownHtml).toContain("Следующий чекпоинт откроется");
    expect(cooldownHtml).not.toContain("path-checkpoint-button");

    const passed = { ...response, checkpoints: [checkpoint({ status: "passed", mastered_count: 4, question_total: 5, passed_at: "2026-09-11T00:00:00Z" })] };
    const passedHtml = renderToStaticMarkup(<TopicPathScreen path={passed} onStartCheckpoint={vi.fn()} />);
    expect(passedHtml).toContain("path-checkpoint is-passed");
    expect(passedHtml).toContain("Пройден · 4/5");

    const locked = { ...response, checkpoints: [checkpoint({ status: "locked" })] };
    const lockedHtml = renderToStaticMarkup(<TopicPathScreen path={locked} onStartCheckpoint={vi.fn()} />);
    expect(lockedHtml).toContain("path-checkpoint is-locked");
    expect(lockedHtml).not.toContain("path-checkpoint-button");
  });

  it("launches the checkpoint for the tapped unit", () => {
    const onStart = vi.fn();
    const withCheckpoint = { ...response, checkpoints: [checkpoint({ unit_index: 0, topic_to: 1 })] };
    const container = document.createElement("div");
    const root = createRoot(container);
    act(() => { root.render(<TopicPathScreen path={withCheckpoint} onStartCheckpoint={onStart} />); });
    const button = container.querySelector<HTMLButtonElement>(".path-checkpoint-button");
    expect(button).not.toBeNull();
    act(() => { button!.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(onStart).toHaveBeenCalledWith(0);
    act(() => { root.unmount(); });
  });
});