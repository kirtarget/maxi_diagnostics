import type { DailyPlanDetail, DailyPlanTask, PlanReason, PlanStatus } from "./types";

export type PlanScreenState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: DailyPlanDetail };

const REASONS: readonly PlanReason[] = ["mistake_review", "growth_topic"];
const STATUSES: readonly PlanStatus[] = ["ready", "done", "no_diagnostic"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function nonnegativeInteger(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const normalized = Math.trunc(value);
  return normalized >= 0 ? normalized : null;
}

function nullableString(value: unknown): string | null | undefined {
  if (value === null) return null;
  return typeof value === "string" ? value : undefined;
}

function parseTask(value: unknown): DailyPlanTask | null {
  if (!isRecord(value)) return null;
  if (typeof value.question_id !== "string" || !value.question_id) return null;
  if (typeof value.topic !== "string" || typeof value.completed !== "boolean") return null;
  const reason = REASONS.find((candidate) => candidate === value.reason) ?? "growth_topic";
  return {
    question_id: value.question_id,
    topic: value.topic,
    reason,
    completed: value.completed,
  };
}

/**
 * Accept only the public plan projection. The server owns task order, the
 * reason for each task and what counts as done, so nothing here re-derives
 * those; a malformed field rejects the whole response instead of guessing.
 */
export function parseDailyPlan(payload: unknown): DailyPlanDetail | null {
  if (!isRecord(payload)) return null;
  const status = STATUSES.find((candidate) => candidate === payload.status);
  if (!status) return null;
  const planDate = nullableString(payload.plan_date);
  const diagnosticId = nullableString(payload.diagnostic_id);
  const subject = nullableString(payload.subject);
  const exam = nullableString(payload.exam);
  if (planDate === undefined || diagnosticId === undefined) return null;
  if (subject === undefined || exam === undefined) return null;
  const total = nonnegativeInteger(payload.total);
  const completed = nonnegativeInteger(payload.completed);
  if (total === null || completed === null) return null;
  if (!Array.isArray(payload.questions)) return null;
  const questions: DailyPlanTask[] = [];
  for (const entry of payload.questions) {
    const task = parseTask(entry);
    if (!task) return null;
    questions.push(task);
  }
  return {
    plan_date: planDate,
    diagnostic_id: diagnosticId,
    subject,
    exam,
    total,
    completed,
    status,
    questions,
  };
}
