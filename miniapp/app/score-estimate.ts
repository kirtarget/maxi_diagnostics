import type { ForecastKind, ScoreEstimate } from "./types";

/**
 * Wording for the estimated exam score. Mirrors backend/diagnostic/score_text.py,
 * and reads persisted snapshots, so every input may be missing or malformed.
 */

function plural(count: number, one: string, few: string, many: string): string {
  const hundreds = Math.abs(count) % 100;
  if (hundreds >= 11 && hundreds <= 14) return many;
  const remainder = Math.abs(count) % 10;
  if (remainder === 1) return one;
  if (remainder >= 2 && remainder <= 4) return few;
  return many;
}

function isInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

export function normalizedEstimate(value: unknown): ScoreEstimate | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const candidate = value as Partial<ScoreEstimate>;
  if (candidate.kind !== "test_score" && candidate.kind !== "grade") return null;
  if (!isInteger(candidate.value) || candidate.value < 0) return null;
  if (!isInteger(candidate.sample_size) || candidate.sample_size <= 0) return null;
  return candidate as ScoreEstimate;
}

export function estimateHeadline(value: unknown, exam?: string | null): string | null {
  const estimate = normalizedEstimate(value);
  if (estimate === null) return null;
  if (estimate.kind === "grade") return `отметка ${estimate.value}`;
  const unit = plural(estimate.value, "балл", "балла", "баллов");
  const examName = typeof exam === "string" ? exam.trim() : "";
  return `≈ ${estimate.value} ${unit} ${examName}`.trim();
}

export function estimateCaption(value: unknown): string | null {
  const estimate = normalizedEstimate(value);
  if (estimate === null) return null;
  const unit = plural(estimate.sample_size, "заданию", "заданиям", "заданиям");
  return `ориентировочно, по ${estimate.sample_size} ${unit}`;
}

/** Noun printed under a forecast number, in the unit the forecast is measured in. */
export function forecastUnitLabel(kind: ForecastKind | undefined, value: number): string {
  if (kind === "grade") return "отметка";
  return plural(value, "балл", "балла", "баллов");
}
