export type GameplayProfilePayload = {
  completion_count?: unknown;
  achievement_keys?: unknown;
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

  return {
    completionCount,
    level,
    levelLabel: LEVELS[level - 1].label,
    levelProgress: progressFor(completionCount, level),
    ...onboardingFor(completionCount),
    unlockedAchievements,
  };
}
