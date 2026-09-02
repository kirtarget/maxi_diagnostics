import type { QuestionSourceAttribution } from "./types";

export function hasApprovedPrimaryScore(source: QuestionSourceAttribution | undefined): boolean {
  return source?.approval_status === "approved";
}

export function primaryScoreLabel(maxPrimaryScore: number): string {
  return `до ${maxPrimaryScore} ${maxPrimaryScore === 1 ? "первичного балла" : "первичных баллов"}`;
}

export function PrimaryScoreBadge({ maxPrimaryScore, earnedPrimaryScore }: { maxPrimaryScore?: number | null; earnedPrimaryScore?: number | null }) {
  if (!Number.isInteger(maxPrimaryScore) || (maxPrimaryScore ?? 0) <= 0) return null;
  const earned = Number.isInteger(earnedPrimaryScore) && (earnedPrimaryScore ?? -1) >= 0
    ? Math.min(earnedPrimaryScore!, maxPrimaryScore!)
    : null;
  const label = earned === null
    ? primaryScoreLabel(maxPrimaryScore!)
    : `${earned} из ${maxPrimaryScore} ${maxPrimaryScore === 1 ? "первичного балла" : "первичных баллов"}`;
  return <span className="primary-score-badge">{label}</span>;
}
