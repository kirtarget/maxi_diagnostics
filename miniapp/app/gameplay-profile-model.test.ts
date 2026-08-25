import { describe, expect, it } from "vitest";
import { gameplayProfileView } from "./gameplay-profile-model";

describe("gameplayProfileView", () => {
  it("builds the new-user view from an empty profile", () => {
    expect(gameplayProfileView({ completion_count: 0, achievement_keys: [] })).toEqual({
      completionCount: 0,
      level: 1,
      levelLabel: "Первый шаг",
      levelProgress: 0,
      onboardingState: "new",
      onboardingLabel: "Начните с первой диагностики",
      unlockedAchievements: [],
    });
  });

  it("derives level progress and the first-completion onboarding state", () => {
    const view = gameplayProfileView({
      completion_count: 2,
      achievement_keys: ["first_diagnostic_completed"],
    });

    expect(view.level).toBe(2);
    expect(view.levelLabel).toBe("Исследователь");
    expect(view.levelProgress).toBe(50);
    expect(view.onboardingState).toBe("returning");
    expect(view.unlockedAchievements).toEqual([
      {
        key: "first_diagnostic_completed",
        title: "Первое завершение",
        description: "Первая диагностика завершена, точка старта зафиксирована.",
      },
    ]);
  });

  it("caps the final level and ignores unsupported or malformed values", () => {
    expect(gameplayProfileView({ completion_count: Number.POSITIVE_INFINITY, achievement_keys: "first_diagnostic_completed" })).toEqual(
      gameplayProfileView({ completion_count: 0, achievement_keys: [] }),
    );
    expect(gameplayProfileView({ completion_count: 999_999, achievement_keys: ["unknown", 7, "first_diagnostic_completed"] })).toMatchObject({
      completionCount: 100_000,
      level: 5,
      levelProgress: 100,
      onboardingState: "returning",
      unlockedAchievements: [expect.objectContaining({ key: "first_diagnostic_completed" })],
    });
  });
});
