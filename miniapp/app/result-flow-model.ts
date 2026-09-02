import { normalizedEstimate } from "./score-estimate";
import type {
  ForecastKind, ForecastPoint, ReviewResponse, ServerResult, ServerTopic,
} from "./types";

type ResultWithForecast = Pick<ServerResult, "score" | "forecast" | "estimate">;
type GrowthTopic = ServerTopic | string;

export type TopicRecommendation = {
  heading: "Тема для повторения" | "Стоит повторить";
  topics: string[];
};

export type PersonalRouteAction = {
  id: "close-topic" | "strengthen-topic" | "recheck";
  title: string;
  description: string;
};

export type PdfStatusCopy = {
  title: string;
  description: string;
  action?: string;
};

export type ResultGameAchievement = {
  id: "first_step" | "steady_base" | "topic_scout";
  title: string;
  description: string;
  earned: boolean;
};

export type ResultGameSummary = {
  points: number;
  level: number;
  levelTitle: string;
  levelProgress: number;
  pointsToNextLevel: number;
  achievements: ResultGameAchievement[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNumericValue(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function boundedInteger(value: number, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!isNumericValue(value)) return 0;
  return Math.min(Math.max(Math.trunc(value), 0), maximum);
}

function topicCount(topics: GrowthTopic[]): number {
  return topics
    .map((topic) => typeof topic === "string" ? topic : topic.topic)
    .map((topic) => topic.trim())
    .filter(Boolean)
    .filter((topic, index, values) => values.indexOf(topic) === index)
    .length;
}

export function resultGameSummary(result: Pick<ServerResult, "score" | "max_score" | "correct_count" | "question_count" | "strong_topics" | "growth_topics">): ResultGameSummary {
  const maxScore = isNumericValue(result.max_score) && result.max_score > 0 ? result.max_score : 0;
  const score = maxScore > 0 && isNumericValue(result.score)
    ? Math.min(Math.max(result.score, 0), maxScore)
    : 0;
  const points = maxScore > 0 ? Math.round((score / maxScore) * 100) : 0;
  const level = points === 100 ? 5 : Math.floor(points / 25) + 1;
  const levelStart = (level - 1) * 25;
  const nextLevelPoints = level === 5 ? 100 : level * 25;
  const levelProgress = level === 5
    ? 100
    : Math.round(((points - levelStart) / (nextLevelPoints - levelStart)) * 100);
  const questionCount = boundedInteger(result.question_count);
  const correctCount = boundedInteger(result.correct_count, questionCount);
  const ratio = questionCount > 0 ? correctCount / questionCount : 0;
  const topics = topicCount([...result.strong_topics, ...result.growth_topics]);

  return {
    points,
    level,
    levelTitle: ["Старт диагностики", "Первые опоры", "Уверенная база", "Сильный темп", "Максимум этой попытки"][level - 1],
    levelProgress,
    pointsToNextLevel: Math.max(nextLevelPoints - points, 0),
    achievements: [
      {
        id: "first_step",
        title: "Первый шаг",
        description: "Диагностика завершена, точка старта зафиксирована.",
        earned: questionCount > 0,
      },
      {
        id: "steady_base",
        title: "Устойчивая база",
        description: "Не менее половины заданий этой диагностики решены верно.",
        earned: questionCount > 0 && ratio >= 0.5,
      },
      {
        id: "topic_scout",
        title: "Исследователь тем",
        description: "Карта тем этой диагностики помогает выбрать следующий шаг.",
        earned: topics > 0,
      },
    ],
  };
}

function persistedForecastPoints(forecast: ResultWithForecast["forecast"]): ForecastPoint[] {
  if (!forecast || !isRecord(forecast)) return [];
  if (Array.isArray(forecast.points)) {
    return forecast.points.flatMap((point) => (
      isRecord(point) &&
      typeof point.id === "string" &&
      typeof point.label === "string" &&
      isNumericValue(point.value)
        ? [{ id: point.id, label: point.label, value: point.value }]
        : []
    ));
  }
  return Object.entries(forecast).flatMap(([label, value]) => (
    isNumericValue(value) ? [{ id: label, label, value }] : []
  ));
}

export function forecastKind(result: ResultWithForecast): ForecastKind {
  const forecast = result.forecast;
  if (isRecord(forecast) && (forecast.kind === "test_score" || forecast.kind === "grade")) {
    return forecast.kind;
  }
  return "accuracy_percent";
}

export function forecastTrajectory(result: ResultWithForecast): ForecastPoint[] {
  const estimate = normalizedEstimate(result.estimate);
  const currentValue = estimate !== null && forecastKind(result) !== "accuracy_percent"
    ? estimate.value
    : result.score;
  const current = isNumericValue(currentValue)
    ? [{ id: "current", label: "Сейчас", value: currentValue }]
    : [];
  return [...current, ...persistedForecastPoints(result.forecast).slice(0, 2)];
}

function topicName(topic: GrowthTopic): string | null {
  const value = typeof topic === "string" ? topic : topic.topic;
  const normalized = value.trim();
  return normalized ? normalized : null;
}

export function topicRecommendation(growthTopics: GrowthTopic[]): TopicRecommendation | null {
  const topics = growthTopics
    .map(topicName)
    .filter((topic): topic is string => topic !== null)
    .filter((topic, index, values) => values.indexOf(topic) === index)
    .slice(0, 2);
  if (topics.length === 0) return null;
  const supported = growthTopics.some((topic) => (
    typeof topic !== "string"
    && typeof topic.question_count === "number"
    && topic.question_count >= 2
  ));
  return { heading: supported ? "Тема для повторения" : "Стоит повторить", topics };
}

export function personalRoute(growthTopics: GrowthTopic[]): PersonalRouteAction[] {
  const topicActions = growthTopics
    .map(topicName)
    .filter((topic): topic is string => topic !== null)
    .filter((topic, index, topics) => topics.indexOf(topic) === index)
    .slice(0, 2)
    .map((topic, index) => index === 0
      ? {
        id: "close-topic" as const,
        title: `Закрыть тему «${topic}»`,
        description: "Повтори базовые конструкции и реши короткий набор заданий.",
      }
      : {
        id: "strengthen-topic" as const,
        title: `Укрепить тему «${topic}»`,
        description: "Собери ключевые правила и закрепи их практикой.",
      });

  const recheck: PersonalRouteAction = {
    id: "recheck",
    title: "Проверить рост",
    description: "Повтори диагностику через месяц и сравни результат.",
  };

  return [
    ...topicActions,
    recheck,
  ].slice(0, 3);
}

export function pdfStatusCopy(status: ReviewResponse["pdf_status"]): PdfStatusCopy {
  switch (status) {
    case "pending":
      return {
        title: "Готовим PDF для Telegram",
        description: "Результат и разбор уже сохранены.",
      };
    case "sending":
      return {
        title: "Отправляем PDF в Telegram",
        description: "Проверяем доставку документа.",
      };
    case "sent":
      return {
        title: "PDF отправлен в Telegram",
        description: "Результат, ответы и разбор сохранены в чате.",
      };
    case "failed":
      return {
        title: "PDF пока не отправлен",
        description: "Документ сохранён; попробуйте проверить статус позже.",
        action: "Проверить статус",
      };
    case "abandoned":
      return {
        title: "PDF не удалось отправить",
        description: "Результат и разбор остаются доступны в приложении.",
        action: "Проверить статус",
      };
  }
}
