import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { BottomNav, GameplayHomeScreen, GameplayProfileScreen, ModeScreen, SubjectsScreen } from "./navigation-screens";
import { gameplayProfileView } from "./gameplay-profile-model";

const labels = { start_diagnostic: "Начать диагностику", full_result: "Полный результат", quick_result: "Быстрый результат", choose_label: "Выбрать", back: "Назад" } as never;
const diagnostic = { id: "math", content_version: "v1", exam: "ЕГЭ", subject: "Математика", mark: "М", quick_count: 3, full_count: 18, question_count: 18 };

describe("KIR-233 navigation surfaces", () => {
  it("renders one home primary and gives resume precedence", () => {
    const html = renderToStaticMarkup(<GameplayHomeScreen
      diagnostics={[diagnostic]}
      resumableAttempt={{ attempt_id: "attempt-1", diagnostic_id: "math", content_version: "v1", mode: "quick", status: "in_progress", question_index: 2, question_count: 18, progress_revision: 1, subject: "Математика" }}
      dailyPlan={{ status: "ready", diagnostic_id: "math", subject: "Математика", exam: "ЕГЭ", plan_date: null, total: 1, completed: 0 }}
      labels={labels} profile={gameplayProfileView({ completion_count: 1, achievement_keys: [] })}
      onStart={vi.fn()} onResume={vi.fn()} onStartPlan={vi.fn()} onOpenProfile={vi.fn()}
    />);
    expect((html.match(/class="primary-button/g) ?? [])).toHaveLength(1);
    expect(html).toContain("Продолжить: Математика, задание 3 из 18");
    expect(html).not.toContain("План на сегодня");
  });

  it("keeps the home block order and result facts", () => {
    const html = renderToStaticMarkup(<GameplayHomeScreen
      diagnostics={[diagnostic]}
      lastSubject="Математика"
      results={[{ attempt_id: "done", diagnostic_id: "math", content_version: "v1", mode: "full", status: "completed", question_index: 18, question_count: 18, progress_revision: 1, subject: "Математика", completed_at: "2026-09-07T12:00:00Z", result: { diagnostic_id: "math", mode: "full", question_count: 18, correct_count: 1, skipped_count: 0, score: 1, max_score: 18, score_unit: "балл", strong_topics: [], growth_topics: [] } }]}
      labels={labels} profile={gameplayProfileView({ completion_count: 1, achievement_keys: [] })}
      onStart={vi.fn()} onOpenProfile={vi.fn()} offers={[{ id: "offer", label: "Курс", button: "Открыть", url: "https://school.example/course" }]}
    />);
    expect(html.indexOf("gameplay-home-hero")).toBeLessThan(html.indexOf("gameplay-home-cta"));
    expect(html.indexOf("gameplay-home-cta")).toBeLessThan(html.indexOf("gameplay-next-subject"));
    expect(html.indexOf("gameplay-next-subject")).toBeLessThan(html.indexOf("Доступные предметы"));
    expect(html.indexOf("Доступные предметы")).toBeLessThan(html.indexOf("Мои результаты"));
    expect(html.indexOf("Мои результаты")).toBeLessThan(html.indexOf("offer-surface-home"));
    expect(html.indexOf("offer-surface-home")).toBeLessThan(html.indexOf("gameplay-profile-card"));
    expect(html).not.toContain("gameplay-cta-row");
    expect(html).not.toContain("gameplay-trainer-cta");
    expect(html).not.toContain("gameplay-league-cta");
    expect(html).toContain("1 из 18 · 6 %");
    expect(html).toContain("7 сентября");
  });

  it("shows the selected subject formats with real counts and duration", () => {
    const html = renderToStaticMarkup(<ModeScreen diagnostic={diagnostic} labels={labels} onBack={vi.fn()} onSelect={vi.fn()} />);
    expect(html).toContain("3 задания · ~5 мин");
    expect(html).toContain("18 заданий · ~30 мин");
    expect(html).toContain("3 из 18");
    expect(html).toContain("18 из 18");
    expect(html).not.toContain("quick");
    expect(html).not.toContain("full");
  });

  it("keeps exam tabs and subjects free of technical format slugs", () => {
    const html = renderToStaticMarkup(<SubjectsScreen diagnostics={[diagnostic, { ...diagnostic, id: "oge", exam: "ОГЭ" }]} exam="ОГЭ" labels={labels} onBack={vi.fn()} onExam={vi.fn()} onSelect={vi.fn()} />);
    expect(html).toContain("ОГЭ");
    expect(html).toContain("ЕГЭ");
    expect(html).not.toContain("quick");
    expect(html).not.toContain("full");
  });

  it("keeps onboarding steps honest", () => {
    const subjects = renderToStaticMarkup(<SubjectsScreen diagnostics={[diagnostic]} exam="ЕГЭ" labels={labels} onBack={vi.fn()} onExam={vi.fn()} onSelect={vi.fn()} />);
    const formats = renderToStaticMarkup(<ModeScreen diagnostic={diagnostic} labels={labels} onBack={vi.fn()} onSelect={vi.fn()} />);
    expect(subjects).toContain("Шаг 1 из 2");
    expect(formats).toContain("Шаг 2 из 2");
  });

  it("renders all bottom navigation destinations", () => {
    const html = renderToStaticMarkup(<BottomNav screen="home" onNavigate={vi.fn()} />);
    expect(html).toContain("Главная");
    expect(html).toContain("Тренажёр");
    expect(html).toContain("Лига");
    expect(html).toContain("Профиль");
    expect(html).toContain('aria-current="page"');
  });

  it("renders unlocked and locked achievements as distinct states", () => {
    const html = renderToStaticMarkup(<GameplayProfileScreen profile={gameplayProfileView({ completion_count: 1, achievement_keys: ["first_diagnostic_completed"] })} onBack={vi.fn()} onStart={vi.fn()} />);
    expect(html).toContain("is-unlocked");
    expect(html).toContain("is-locked");
    expect(html).toContain("Заверши три диагностики, чтобы открыть достижение.");
  });

  it("pins dashboard values to readable ink inside the light surface cards", () => {
    const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");
    const rule = css.match(/\.gameplay-dashboard > div\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toContain("color: var(--ink);");
    expect(rule).toContain("background: var(--surface);");
  });
});
