import type { ForecastPoint, ReviewResponse, ServerResult, ServerTopic } from "./types";

type ResultWithForecast = Pick<ServerResult, "score" | "forecast">;
type GrowthTopic = ServerTopic | string;

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNumericValue(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
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

export function forecastTrajectory(result: ResultWithForecast): ForecastPoint[] {
  const current = isNumericValue(result.score)
    ? [{ id: "current", label: "Сейчас", value: result.score }]
    : [];
  return [...current, ...persistedForecastPoints(result.forecast).slice(0, 2)];
}

function topicName(topic: GrowthTopic): string | null {
  const value = typeof topic === "string" ? topic : topic.topic;
  const normalized = value.trim();
  return normalized ? normalized : null;
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

  return [
    ...topicActions,
    {
      id: "recheck",
      title: "Проверить рост",
      description: "Повтори диагностику через месяц и сравни результат.",
    },
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
