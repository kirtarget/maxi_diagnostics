import type { DailyPlanSummary, DiagnosticMode, PublicDiagnosticSummary, Screen, ServerAttempt } from "./types";
import { plural } from "./text-utils";

/** Navigation is a small state machine. A format is meaningful only after a subject is selected. */
export type NavigationSelection = {
  exam: string;
  diagnosticId: string | null;
  mode: DiagnosticMode | null;
};

export type NavigationIntent = { kind: "trainer" } | null;

export type HomePrimaryAction =
  | { kind: "resume"; label: string; attempt: ServerAttempt }
  | { kind: "daily-plan"; label: string; plan: DailyPlanSummary }
  | { kind: "new-diagnostic"; label: string };

export const SUBMIT_MINIMUM_MS = 300;

export function submitPresentation(elapsedMs: number): { remainingMs: number; showWarning: boolean } {
  const elapsed = Math.max(0, elapsedMs);
  return { remainingMs: Math.max(0, SUBMIT_MINIMUM_MS - elapsed), showWarning: elapsed >= SUBMIT_MINIMUM_MS };
}

export const examPreferenceKey = (schoolId: string): string => `diagnostic-exam-preference:${schoolId}`;

export function shouldShowBottomNav(screen: Screen): boolean {
  return screen !== "question" && screen !== "trainer" && screen !== "submitting" && screen !== "session-complete" && screen !== "checkpoint-result";
}

export function readExamPreference(schoolId: string, storage?: Storage): string | null {
  try {
    const target = storage ?? (typeof window === "undefined" ? undefined : window.localStorage);
    if (!target) return null;
    const value = target.getItem(examPreferenceKey(schoolId));
    return value?.trim() || null;
  } catch {
    return null;
  }
}

export function writeExamPreference(schoolId: string, exam: string, storage?: Storage): void {
  if (!exam.trim()) return;
  try {
    const target = storage ?? (typeof window === "undefined" ? undefined : window.localStorage);
    target?.setItem(examPreferenceKey(schoolId), exam);
  } catch {
    return;
  }
}

/** The stable estimate is five minutes per three questions, rounded to a whole minute. */
export function formatDiagnosticCount(mode: DiagnosticMode, diagnostic: PublicDiagnosticSummary): string {
  return `${mode === "quick" ? diagnostic.quick_count : diagnostic.full_count} из ${diagnostic.full_count}`;
}

export function formatDiagnosticDuration(mode: DiagnosticMode, diagnostic: PublicDiagnosticSummary): string {
  const count = mode === "quick" ? diagnostic.quick_count : diagnostic.full_count;
  const minutes = Math.max(5, Math.round((count * 5) / 3));
  return `~${minutes} мин`;
}

export function formatDiagnosticMeta(mode: DiagnosticMode, diagnostic: PublicDiagnosticSummary): string {
  const count = mode === "quick" ? diagnostic.quick_count : diagnostic.full_count;
  return `${count} ${plural(count, ["задание", "задания", "заданий"])} · ${formatDiagnosticDuration(mode, diagnostic)}`;
}

export function homePrimaryAction({
  resumableAttempt,
  dailyPlan,
}: {
  resumableAttempt?: ServerAttempt | null;
  dailyPlan?: DailyPlanSummary | null;
}): HomePrimaryAction {
  if (resumableAttempt?.status === "in_progress") {
    const subject = resumableAttempt.subject ?? "диагностика";
    const current = Math.min(Math.max(resumableAttempt.question_index + 1, 1), Math.max(resumableAttempt.question_count, 1));
    return {
      kind: "resume",
      label: `Продолжить: ${subject}, задание ${current} из ${resumableAttempt.question_count}`,
      attempt: resumableAttempt,
    };
  }
  if (dailyPlan?.status === "ready" && dailyPlan.diagnostic_id) {
    return { kind: "daily-plan", label: `Задания на сегодня: ${dailyPlan.completed} из ${dailyPlan.total}`, plan: dailyPlan };
  }
  return { kind: "new-diagnostic", label: "Начать диагностику" };
}

export function resultFact(attempt: ServerAttempt): string {
  const result = attempt.result;
  if (!result) return "";
  const percent = result.question_count > 0 ? Math.round((result.correct_count / result.question_count) * 100) : 0;
  return `${result.correct_count} из ${result.question_count} · ${percent} %`;
}

export function formatCompletedDate(value: string | undefined): string {
  if (!value) return "Дата не указана";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" }).format(date);
}
