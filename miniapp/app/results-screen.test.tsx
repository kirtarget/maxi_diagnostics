import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ResultsScreen } from "./results-screen";
import type { ServerAttempt } from "./types";

const completed: ServerAttempt = {
  attempt_id: "a1",
  diagnostic_id: "phys",
  content_version: "v1",
  mode: "quick",
  status: "completed",
  question_index: 5,
  question_count: 5,
  progress_revision: 3,
  subject: "Физика",
  exam: "ОГЭ",
  completed_at: "2026-09-10T10:00:00Z",
  result: {
    diagnostic_id: "phys",
    mode: "quick",
    question_count: 5,
    correct_count: 3,
    skipped_count: 0,
    score: 3,
    max_score: 5,
    score_unit: "балл",
    strong_topics: [],
    growth_topics: [],
  },
};

describe("ResultsScreen", () => {
  it("lists completed diagnostics with their accuracy fact", () => {
    const html = renderToStaticMarkup(<ResultsScreen results={[completed]} onOpenResult={vi.fn()} onStartDiagnostic={vi.fn()} />);
    expect(html).toContain("Физика");
    expect(html).toContain("3 из 5 · 60 %");
  });

  it("shows an empty state that invites a diagnostic", () => {
    const html = renderToStaticMarkup(<ResultsScreen results={[]} onOpenResult={vi.fn()} onStartDiagnostic={vi.fn()} />);
    expect(html).toContain("Пока нет завершённых диагностик");
    expect(html).toContain("Пройти диагностику");
  });
});
