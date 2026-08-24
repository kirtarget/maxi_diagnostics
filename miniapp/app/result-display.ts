import type { ServerResult } from "./types";

export function shouldShowResultMetrics(
  result: Pick<ServerResult, "correct_count" | "score">,
): boolean {
  return Number.isFinite(result.score)
    && result.score >= 0
    && Number.isFinite(result.correct_count)
    && result.correct_count >= 0;
}
