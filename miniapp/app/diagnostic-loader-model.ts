import type { PublicDiagnostic, PublicDiagnosticSummary } from "./types";

export type DiagnosticLoadIntent = "new" | "resume";

export type DiagnosticLoadState =
  | { phase: "idle" }
  | {
    phase: "loading";
    requestId: number;
    summary: PublicDiagnosticSummary;
    intent: DiagnosticLoadIntent;
  }
  | {
    phase: "ready";
    requestId: number;
    diagnostic: PublicDiagnostic;
    intent: DiagnosticLoadIntent;
  }
  | {
    phase: "error";
    requestId: number;
    summary: PublicDiagnosticSummary;
    intent: DiagnosticLoadIntent;
    message: string;
  };

export type DiagnosticLoadAction =
  | {
    type: "load";
    requestId: number;
    summary: PublicDiagnosticSummary;
    intent: DiagnosticLoadIntent;
  }
  | { type: "loaded"; requestId: number; diagnostic: PublicDiagnostic }
  | { type: "failed"; requestId: number; message: string }
  | { type: "reset" };

export const diagnosticLoadInitialState: DiagnosticLoadState = { phase: "idle" };

export function diagnosticSummaryKey(summary: PublicDiagnosticSummary): string {
  return `${summary.id}:${summary.content_version}`;
}

export function diagnosticLoadReducer(
  state: DiagnosticLoadState,
  action: DiagnosticLoadAction,
): DiagnosticLoadState {
  if (action.type === "reset") return diagnosticLoadInitialState;
  if (action.type === "load") {
    return {
      phase: "loading",
      requestId: action.requestId,
      summary: action.summary,
      intent: action.intent,
    };
  }
  if (state.phase !== "loading" || state.requestId !== action.requestId) return state;
  if (action.type === "loaded") {
    return {
      phase: "ready",
      requestId: action.requestId,
      diagnostic: action.diagnostic,
      intent: state.intent,
    };
  }
  return {
    phase: "error",
    requestId: action.requestId,
    summary: state.summary,
    intent: state.intent,
    message: action.message,
  };
}
