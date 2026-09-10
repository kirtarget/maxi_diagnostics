import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { SessionCompleteScreen } from "./session-complete-screen";
import type { SessionCompleteView } from "./session-complete-model";

const view: SessionCompleteView = {
  topic: "Тепловые явления",
  solved: 4,
  answered: 5,
  size: 5,
  xpEarned: 40,
  streakDays: 5,
  streakGrew: true,
  masteryPercent: 58,
  masteryBefore: 42,
  masteryDelta: 16,
  toRepeat: 1,
  nextSize: 5,
  nextTopic: "Тепловые явления",
};

describe("SessionCompleteScreen", () => {
  it("celebrates the session with streak, xp and a solved count", () => {
    const html = renderToStaticMarkup(<SessionCompleteScreen view={view} onHome={vi.fn()} onReview={vi.fn()} />);
    expect(html).toContain("Сессия закончена");
    expect(html).toContain("5 дней подряд");
    expect(html).toContain("+1 день");
    expect(html).toContain("+40");
    expect(html).toContain("4/5");
  });

  it("shows topic growth and the mistakes to repeat, but never an accuracy percent", () => {
    const html = renderToStaticMarkup(<SessionCompleteScreen view={view} onHome={vi.fn()} onReview={vi.fn()} />);
    expect(html).toContain("было 42% → стало 58%");
    expect(html).toContain("+16%");
    expect(html).toContain("Над чем ещё поработать");
    expect(html).toContain("Завтра: 5 заданий");
    // The session tally is a count, so no "N%" accuracy sneaks onto this screen.
    expect(html).not.toContain("точность");
  });

  it("offers home and session review actions", () => {
    const html = renderToStaticMarkup(<SessionCompleteScreen view={view} onHome={vi.fn()} onReview={vi.fn()} />);
    expect(html).toContain("На главную");
    expect(html).toContain("Разбор этой сессии");
  });

  it("omits the review button and growth panels when data is thin", () => {
    const thin: SessionCompleteView = { ...view, masteryPercent: null, masteryBefore: null, masteryDelta: null, toRepeat: 0, streakGrew: false, nextSize: null, nextTopic: null };
    const html = renderToStaticMarkup(<SessionCompleteScreen view={thin} onHome={vi.fn()} />);
    expect(html).not.toContain("Разбор этой сессии");
    expect(html).not.toContain("Над чем ещё поработать");
    expect(html).not.toContain("Завтра:");
    expect(html).not.toContain("+1 день");
  });
});
