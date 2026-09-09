import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GameplayHomeScreen, SubjectsScreen, WelcomeScreen } from "./navigation-screens";
import { gameplayProfileView } from "./gameplay-profile-model";

describe("gameplay dashboard", () => {
  const diagnostics = [{
    id: "math",
    content_version: "v1",
    exam: "ОГЭ",
    subject: "Математика",
    mark: "М",
    quick_count: 3,
    full_count: 12,
    question_count: 12,
  }];

  it("advertises only the quick diagnostic range during onboarding", () => {
    const html = renderToStaticMarkup(<WelcomeScreen
      diagnostics={[...diagnostics, { ...diagnostics[0], id: "second", quick_count: 2, full_count: 26 }]}
      labels={{} as never} links={{ privacy: "#", support: "#" } as never} onStart={() => undefined}
    />);
    expect(html).toContain("2–3");
    expect(html).not.toContain("2–26");
  });

  it.each([[1, "задание"], [2, "задания"], [3, "задания"], [5, "заданий"], [11, "заданий"]])("declines %s questions and describes answer review", (count, word) => {
    const html = renderToStaticMarkup(<SubjectsScreen
      diagnostics={[{ ...diagnostics[0], quick_count: count as number }]}
      exam="ОГЭ" labels={{} as never} mode="quick" onBack={() => undefined}
      onExam={() => undefined} onSelect={() => undefined}
    />);
    expect(html).toContain(`${count} ${word} · разбор ответов`);
    expect(html).not.toContain("полный разбор");
  });

  it("keeps the home screen focused on the streak, trainer allowance, and next action", () => {
    const html = renderToStaticMarkup(<GameplayHomeScreen
      diagnostics={diagnostics}
      labels={{ start_diagnostic: "Начать" } as never}
      profile={gameplayProfileView({
        xp_total: 140,
        level: 2,
        level_progress: 27,
        streak_days: 4,
        lives_remaining: 5,
        daily_goal: { date: null, target: 1, progress: 1, complete: true },
        quest: { key: "complete_3_activities", date: null, target: 3, progress: 2 },
        completion_count: 1,
      })}
      onStart={() => undefined}
      onOpenProfile={() => undefined}
    />);

    expect(html).toContain("4");
    expect(html).toContain("5</strong><small>ошибок до паузы в тренажёре");
    expect(html).toContain("Выбрать диагностику");
    expect(html).not.toContain("140 XP");
    expect(html).not.toContain("цель дня");
    expect(html).not.toContain("Квест");
    expect(html).not.toContain("Ближайшие диагностики");
  });

  it("does not claim server gameplay facts in the fallback", () => {
    const html = renderToStaticMarkup(<GameplayHomeScreen
      diagnostics={diagnostics}
      labels={{ start_diagnostic: "Начать" } as never}
      profile={gameplayProfileView({ completion_count: 0, achievement_keys: [] })}
      onStart={() => undefined}
      onOpenProfile={() => undefined}
    />);

    expect(html).not.toContain("дней подряд");
    expect(html).not.toContain("Квест");
  });
});
