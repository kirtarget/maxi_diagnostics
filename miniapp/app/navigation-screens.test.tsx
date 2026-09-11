import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { BottomNav, GameplayProfileScreen, ModeScreen, SubjectsScreen } from "./navigation-screens";
import { gameplayProfileView } from "./gameplay-profile-model";

const labels = { start_diagnostic: "Начать диагностику", full_result: "Полный результат", quick_result: "Быстрый результат", choose_label: "Выбрать", back: "Назад" } as never;
const diagnostic = { id: "math", content_version: "v1", exam: "ЕГЭ", subject: "Математика", mark: "М", quick_count: 3, full_count: 18, question_count: 18 };

describe("KIR-233 navigation surfaces", () => {
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
    const html = renderToStaticMarkup(<BottomNav screen="today" onNavigate={vi.fn()} />);
    expect(html).toContain("Сегодня");
    expect(html).toContain("Путь");
    expect(html).toContain("Результаты");
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
