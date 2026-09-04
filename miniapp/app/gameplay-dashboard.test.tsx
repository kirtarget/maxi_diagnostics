import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GameplayHomeScreen } from "./navigation-screens";
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

  it("renders server-owned XP, streak, lives, daily goal, and quest", () => {
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
      })}
      onStart={() => undefined}
      onOpenProfile={() => undefined}
    />);

    expect(html).toContain("140 XP");
    expect(html).toContain("4");
    expect(html).toContain("1/1");
    expect(html).toContain("2/3 активностей");
    expect(html).toContain("жизни");
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
