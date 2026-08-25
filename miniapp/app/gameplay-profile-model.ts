import type { GameplayProfile } from "./types";

export type GameplayProfilePayload = {
  completion_count?: unknown;
  achievement_keys?: unknown;
  xp_total?: unknown;
  level?: unknown;
  level_progress?: unknown;
  streak_days?: unknown;
  lives_remaining?: unknown;
  daily_goal?: unknown;
  quest?: unknown;
};

export type OnboardingState = "new" | "first_completion" | "returning";

export type UnlockedAchievement = {
  key: "first_diagnostic_completed";
  title: string;
  description: string;
};

export type GameplayProfileView = {
  completionCount: number;
  level: number;
  levelLabel: string;
  levelProgress: number;
  onboardingState: OnboardingState;
  onboardingLabel: string;
  unlockedAchievements: UnlockedAchievement[];
  serverBacked: boolean;
  xpTotal?: number;
  streakDays?: number;
  livesRemaining?: number;
  dailyGoal?: GameplayProfile["daily_goal"];
  quest?: GameplayProfile["quest"];
};

const LEVELS = [
  { minimum: 0, label: "Первый шаг" },
  { minimum: 1, label: "Исследователь" },
  { minimum: 3, label: "Практик" },
  { minimum: 5, label: "Уверенный маршрут" },
  { minimum: 10, label: "Мастер диагностики" },
] as const;

const ACHIEVEMENTS: Record<UnlockedAchievement["key"], UnlockedAchievement> = {
  first_diagnostic_completed: {
    key: "first_diagnostic_completed",
    title: "Первое завершение",
    description: "Первая диагностика завершена, точка старта зафиксирована.",
  },
};

function normalizedCompletionCount(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.min(Math.max(Math.trunc(value), 0), 100_000);
}

function normalizedAchievementKeys(value: unknown): Set<string> {
  if (!Array.isArray(value)) return new Set();
  return new Set(value.filter((key): key is string => typeof key === "string"));
}

function normalizedNonnegativeInt(value: unknown, fallback: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return fallback;
  return Math.max(Math.trunc(value), 0);
}

function normalizedServerProfile(payload: GameplayProfilePayload | null | undefined): GameplayProfile | null {
  if (!payload || typeof payload !== "object") return null;
  const dailyGoal = payload.daily_goal;
  if (!dailyGoal || typeof dailyGoal !== "object") return null;
  const goal = dailyGoal as Record<string, unknown>;
  if (
    typeof payload.xp_total !== "number" || !Number.isFinite(payload.xp_total)
    || typeof payload.level !== "number" || !Number.isFinite(payload.level)
    || typeof payload.level_progress !== "number" || !Number.isFinite(payload.level_progress)
    || typeof payload.streak_days !== "number" || !Number.isFinite(payload.streak_days)
    || typeof payload.lives_remaining !== "number" || !Number.isFinite(payload.lives_remaining)
    || typeof goal.target !== "number" || !Number.isFinite(goal.target)
    || typeof goal.progress !== "number" || !Number.isFinite(goal.progress)
    || typeof goal.complete !== "boolean"
  ) return null;
  const quest = payload.quest;
  const normalizedQuest = quest === null ? null : (() => {
    if (!quest || typeof quest !== "object") return null;
    const value = quest as Record<string, unknown>;
    if (typeof value.key !== "string" || typeof value.target !== "number" || !Number.isFinite(value.target) || typeof value.progress !== "number" || !Number.isFinite(value.progress)) return null;
    return {
      key: value.key,
      date: typeof value.date === "string" ? value.date : null,
      target: Math.max(Math.trunc(value.target), 1),
      progress: Math.max(Math.trunc(value.progress), 0),
    };
  })();
  if (quest !== null && normalizedQuest === null) return null;
  return {
    xp_total: normalizedNonnegativeInt(payload.xp_total, 0),
    level: Math.max(Math.trunc(payload.level), 1),
    level_progress: Math.min(Math.max(Math.trunc(payload.level_progress), 0), 100),
    streak_days: normalizedNonnegativeInt(payload.streak_days, 0),
    lives_remaining: Math.min(normalizedNonnegativeInt(payload.lives_remaining, 0), 5),
    daily_goal: {
      date: typeof goal.date === "string" ? goal.date : null,
      target: Math.max(Math.trunc(goal.target), 1),
      progress: Math.max(Math.trunc(goal.progress), 0),
      complete: goal.complete,
    },
    quest: normalizedQuest,
  };
}

function levelFor(completionCount: number): number {
  let level = 1;
  for (const [index, definition] of LEVELS.entries()) {
    if (completionCount >= definition.minimum) level = index + 1;
  }
  return level;
}

function progressFor(completionCount: number, level: number): number {
  if (level === LEVELS.length) return 100;
  const current = LEVELS[level - 1].minimum;
  const next = LEVELS[level].minimum;
  return Math.round(((completionCount - current) / (next - current)) * 100);
}

function onboardingFor(completionCount: number): Pick<GameplayProfileView, "onboardingState" | "onboardingLabel"> {
  if (completionCount === 0) {
    return { onboardingState: "new", onboardingLabel: "Начните с первой диагностики" };
  }
  if (completionCount === 1) {
    return { onboardingState: "first_completion", onboardingLabel: "Первый результат уже готов" };
  }
  return { onboardingState: "returning", onboardingLabel: "Продолжайте свой маршрут" };
}

export function gameplayProfileView(payload: GameplayProfilePayload | null | undefined): GameplayProfileView {
  const completionCount = normalizedCompletionCount(payload?.completion_count);
  const level = levelFor(completionCount);
  const keys = normalizedAchievementKeys(payload?.achievement_keys);
  const unlockedAchievements = (Object.keys(ACHIEVEMENTS) as Array<UnlockedAchievement["key"]>)
    .filter((key) => keys.has(key))
    .map((key) => ACHIEVEMENTS[key]);

  const serverProfile = normalizedServerProfile(payload);
  return {
    completionCount,
    level,
    levelLabel: LEVELS[level - 1].label,
    levelProgress: progressFor(completionCount, level),
    ...onboardingFor(completionCount),
    unlockedAchievements,
    serverBacked: serverProfile !== null,
    ...(serverProfile ? {
      xpTotal: serverProfile.xp_total,
      level: serverProfile.level,
      levelProgress: serverProfile.level_progress,
      streakDays: serverProfile.streak_days,
      livesRemaining: serverProfile.lives_remaining,
      dailyGoal: serverProfile.daily_goal,
      quest: serverProfile.quest,
      levelLabel: LEVELS[serverProfile.level - 1]?.label ?? `Уровень ${serverProfile.level}`,
    } : {}),
  };
}
