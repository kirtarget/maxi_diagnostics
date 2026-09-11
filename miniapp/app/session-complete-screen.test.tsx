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

  it("draws a mastery bar that grows from the old percent to the new one", () => {
    const html = renderToStaticMarkup(<SessionCompleteScreen view={view} onHome={vi.fn()} onReview={vi.fn()} />);
    // The bar animates its width from the before mastery to the after mastery.
    expect(html).toContain("session-mastery-fill");
    expect(html).toContain("--from:42%");
    expect(html).toContain("--to:58%");
  });

  it("starts the mastery bar at zero when there is no earlier snapshot", () => {
    const firstTime: SessionCompleteView = { ...view, masteryBefore: null, masteryDelta: null };
    const html = renderToStaticMarkup(<SessionCompleteScreen view={firstTime} onHome={vi.fn()} />);
    expect(html).toContain("--from:0%");
    expect(html).toContain("--to:58%");
  });

  it("omits the mastery bar when mastery is unknown", () => {
    const thin: SessionCompleteView = { ...view, masteryPercent: null, masteryBefore: null, masteryDelta: null };
    const html = renderToStaticMarkup(<SessionCompleteScreen view={thin} onHome={vi.fn()} />);
    expect(html).not.toContain("session-mastery-fill");
  });

  it("offers home and session review actions", () => {
    const html = renderToStaticMarkup(<SessionCompleteScreen view={view} onHome={vi.fn()} onReview={vi.fn()} />);
    expect(html).toContain("На главную");
    expect(html).toContain("Разбор этой сессии");
  });

  it("keeps the «N из M» tally in the genitive for 1, 2 and 5", () => {
    const one = renderToStaticMarkup(<SessionCompleteScreen view={{ ...view, solved: 0, size: 1 }} onHome={vi.fn()} />);
    expect(one).toContain("0 из 1 задания");
    expect(one).not.toContain("0 из 1 задание ");
    const two = renderToStaticMarkup(<SessionCompleteScreen view={{ ...view, solved: 1, size: 2 }} onHome={vi.fn()} />);
    expect(two).toContain("1 из 2 заданий");
    const five = renderToStaticMarkup(<SessionCompleteScreen view={{ ...view, solved: 4, size: 5 }} onHome={vi.fn()} />);
    expect(five).toContain("4 из 5 заданий");
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
