import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { TodayScreen } from "./today-screen";
import type { TodaySession, TopicPathNode } from "./types";

function pathNode(topic: string, index: number, status: TopicPathNode["status"], mastered = 0, total = 10): TopicPathNode {
  return { topic, index, total, mastered, status, done_at: null };
}

function today(overrides: Partial<TodaySession> = {}): TodaySession {
  return {
    status: "ready",
    diagnostic_id: "phys",
    content_version: "v1",
    subject: "Физика",
    exam: "ОГЭ",
    topic: "Тепловые явления",
    topic_total: 12,
    topic_mastered: 7,
    size: 5,
    estimated_minutes: 4,
    streak_days: 4,
    daily_goal: { date: "2026-09-11", target: 1, progress: 1, complete: true },
    xp_total: 320,
    path: [
      pathNode("Механические явления", 0, "done", 10, 10),
      pathNode("Тепловые явления", 1, "current", 7, 12),
      pathNode("Электромагнитные явления", 2, "locked"),
    ],
    checkpoints: [],
    checkpoint_unit_index: null,
    ...overrides,
  };
}

const noop = vi.fn();

describe("TodayScreen", () => {
  it("shows one occupy CTA with size, topic and estimate", () => {
    const html = renderToStaticMarkup(<TodayScreen today={today()} onStartSession={noop} onOpenPath={noop} onStartOnboarding={noop} />);
    expect(html).toContain("Заниматься");
    expect(html).toContain("5 заданий");
    expect(html).toContain("Тепловые явления");
    expect(html).toContain("~4 мин");
  });

  it("renders the path preview with a link to the full path", () => {
    const html = renderToStaticMarkup(<TodayScreen today={today()} onStartSession={noop} onOpenPath={noop} onStartOnboarding={noop} />);
    expect(html).toContain("Твой путь");
    expect(html).toContain("Весь путь");
    expect(html).toContain("today-path-node is-current");
    expect(html).toContain("today-path-node is-done");
  });

  it("routes to onboarding when there is no diagnostic", () => {
    const html = renderToStaticMarkup(<TodayScreen today={today({ status: "no_diagnostic", topic: null })} onStartSession={noop} onOpenPath={noop} onStartOnboarding={noop} />);
    expect(html).toContain("Пройти диагностику");
    expect(html).not.toContain("Заниматься");
  });

  it("shows a path-complete state with a next action", () => {
    const html = renderToStaticMarkup(<TodayScreen today={today({ status: "path_complete", topic: null })} onStartSession={noop} onOpenPath={noop} onStartOnboarding={noop} />);
    expect(html).toContain("Путь пройден");
    expect(html).toContain("Смотреть путь");
  });
});
