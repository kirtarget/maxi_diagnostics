import { describe, expect, it } from "vitest";

import { parseDailyPlan } from "./plan-model";

const READY = {
  plan_date: "2026-09-02",
  diagnostic_id: "demo-math",
  subject: "Математика",
  exam: "ЕГЭ",
  total: 2,
  completed: 1,
  status: "ready",
  questions: [
    { question_id: "q1", topic: "Дроби", reason: "mistake_review", completed: true },
    { question_id: "q2", topic: "Проценты", reason: "growth_topic", completed: false },
  ],
};

describe("parseDailyPlan", () => {
  it("keeps the server's task order, reasons and completion flags", () => {
    const plan = parseDailyPlan(READY);
    expect(plan?.questions.map((task) => task.question_id)).toEqual(["q1", "q2"]);
    expect(plan?.questions[0].reason).toBe("mistake_review");
    expect(plan?.questions[0].completed).toBe(true);
    expect(plan?.completed).toBe(1);
  });

  it("accepts the empty plan the server returns without a diagnostic", () => {
    const plan = parseDailyPlan({
      plan_date: null, diagnostic_id: null, subject: null, exam: null,
      total: 0, completed: 0, status: "no_diagnostic", questions: [],
    });
    expect(plan?.status).toBe("no_diagnostic");
    expect(plan?.questions).toEqual([]);
  });

  it("falls back to growth_topic for an unknown reason", () => {
    const plan = parseDailyPlan({
      ...READY,
      questions: [{ question_id: "q1", topic: "Дроби", reason: "cosmic_ray", completed: false }],
    });
    expect(plan?.questions[0].reason).toBe("growth_topic");
  });

  it.each([
    ["a missing status", { ...READY, status: undefined }],
    ["an unknown status", { ...READY, status: "queued" }],
    ["a negative total", { ...READY, total: -1 }],
    ["questions that are not a list", { ...READY, questions: {} }],
    ["a task without an id", { ...READY, questions: [{ topic: "Дроби", reason: "growth_topic", completed: false }] }],
    ["a task without a completion flag", { ...READY, questions: [{ question_id: "q1", topic: "Дроби", reason: "growth_topic" }] }],
    ["a non-object payload", "план"],
  ])("rejects %s", (_label, payload) => {
    expect(parseDailyPlan(payload)).toBeNull();
  });
});
