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
      serverBacked: false,
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

  it("prefers the server-owned gameplay projection", () => {
    expect(gameplayProfileView({
      xp_total: 140,
      level: 2,
      level_progress: 27,
      streak_days: 4,
      lives_remaining: 5,
      daily_goal: { date: "2026-08-25", target: 1, progress: 1, complete: true },
      quest: { key: "complete_3_activities", date: "2026-08-25", target: 3, progress: 2 },
    })).toMatchObject({
      serverBacked: true,
      xpTotal: 140,
      level: 2,
      levelProgress: 27,
      streakDays: 4,
      livesRemaining: 5,
      dailyGoal: { target: 1, progress: 1, complete: true },
      quest: { key: "complete_3_activities", progress: 2 },
    });
  });

  it("keeps the completion-only fallback when the server projection is absent", () => {
    expect(gameplayProfileView({ completion_count: 2, achievement_keys: [] })).toMatchObject({
      serverBacked: false,
      completionCount: 2,
    });
    expect(gameplayProfileView({ completion_count: 2, achievement_keys: [] })).not.toHaveProperty("streakDays");
    expect(gameplayProfileView({ completion_count: 2, achievement_keys: [] })).not.toHaveProperty("quest");
  });

  it("retains legacy completion data when merged with server gameplay", () => {
    expect(gameplayProfileView({
      completion_count: 1,
      achievement_keys: ["first_diagnostic_completed"],
      xp_total: 40,
      level: 1,
      level_progress: 40,
      streak_days: 1,
      lives_remaining: 5,
      daily_goal: { date: null, target: 1, progress: 1, complete: true },
      quest: null,
    })).toMatchObject({
      completionCount: 1,
      unlockedAchievements: [expect.objectContaining({ key: "first_diagnostic_completed" })],
      xpTotal: 40,
      serverBacked: true,
    });
  });
});
