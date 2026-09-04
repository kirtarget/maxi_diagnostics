import { describe, expect, it } from "vitest";

import {
  diagnosticLoadInitialState,
  diagnosticLoadReducer,
  diagnosticSummaryKey,
} from "./diagnostic-loader-model";
import type { PublicDiagnostic, PublicDiagnosticSummary } from "./types";

const summary = {
  id: "demo-math",
  content_version: "a".repeat(64),
  exam: "ОГЭ",
  subject: "Математика",
  mark: "М",
  quick_count: 5,
  full_count: 15,
  question_count: 15,
} satisfies PublicDiagnosticSummary;

const diagnostic = {
  ...summary,
  questions: [],
} satisfies PublicDiagnostic;

describe("diagnostic loader model", () => {
  it("ignores a completed request after a newer selection starts", () => {
    let state = diagnosticLoadReducer(diagnosticLoadInitialState, {
      type: "load",
      requestId: 1,
      summary,
      intent: "new",
    });
    state = diagnosticLoadReducer(state, {
      type: "load",
      requestId: 2,
      summary: { ...summary, id: "demo-russian" },
      intent: "new",
    });

    state = diagnosticLoadReducer(state, { type: "loaded", requestId: 1, diagnostic });

    expect(state).toMatchObject({ phase: "loading", requestId: 2 });
  });

  it("keeps the selection and intent when loading fails so retry is possible", () => {
    const loading = diagnosticLoadReducer(diagnosticLoadInitialState, {
      type: "load",
      requestId: 4,
      summary,
      intent: "resume",
    });

    expect(diagnosticLoadReducer(loading, {
      type: "failed",
      requestId: 4,
      message: "offline",
    })).toEqual({
      phase: "error",
      requestId: 4,
      summary,
      intent: "resume",
      message: "offline",
    });
  });

  it("keys cached content by id and version", () => {
    expect(diagnosticSummaryKey(summary)).toBe(`demo-math:${"a".repeat(64)}`);
  });
});
