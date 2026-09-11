import type { TodaySession } from "./types";
import type { TrainerFinishResponse } from "./trainer-model";
import { topicMasteryPercent } from "./today-path-model";

/** Mastery of the trained topic captured before the session started, so the completion screen can show growth. */
export type SessionStartSnapshot = {
  topic: string | null;
  mastered: number;
  total: number;
  streakDays: number;
};

/** Everything the completion screen renders. Accuracy percent stays out of here by design; it lives on the results screen. */
export type SessionCompleteView = {
  topic: string | null;
  /** Session tally as a count, never an accuracy percent. */
  solved: number;
  answered: number;
  size: number;
  xpEarned: number;
  streakDays: number;
  streakGrew: boolean;
  /** Mastery of the trained topic after the session, as a whole percent, or null when unknown. */
  masteryPercent: number | null;
  masteryBefore: number | null;
  /** Percentage points the trained topic grew, when both snapshots are known. */
  masteryDelta: number | null;
  /** Questions that still need a repeat. */
  toRepeat: number;
  /** Tomorrow's session, when the server already knows it. */
  nextSize: number | null;
  nextTopic: string | null;
};

/** Read the trained topic's mastery out of a today response, matching by topic name. */
function masteryOf(today: TodaySession | null, topic: string | null): { percent: number; mastered: number; total: number } | null {
  if (!today) return null;
  if (topic) {
    const node = today.path.find((candidate) => candidate.topic === topic);
    if (node) return { percent: topicMasteryPercent(node.mastered, node.total), mastered: node.mastered, total: node.total };
  }
  if (today.topic_total > 0) {
    return { percent: topicMasteryPercent(today.topic_mastered, today.topic_total), mastered: today.topic_mastered, total: today.topic_total };
  }
  return null;
}

export function sessionCompleteView(
  finish: TrainerFinishResponse,
  before: SessionStartSnapshot | null,
  after: TodaySession | null,
): SessionCompleteView {
  const topic = before?.topic ?? after?.topic ?? null;
  const afterMastery = masteryOf(after, topic);
  const beforePercent = before && before.total > 0 ? topicMasteryPercent(before.mastered, before.total) : null;
  const masteryPercent = afterMastery?.percent ?? beforePercent;
  const masteryDelta = masteryPercent !== null && beforePercent !== null ? masteryPercent - beforePercent : null;
  const streakGrew = before ? after !== null && after.streak_days > before.streakDays : false;
  const streakDays = after?.streak_days ?? before?.streakDays ?? 0;
  return {
    topic,
    solved: finish.correct_count,
    answered: finish.answered_count,
    size: finish.question_count,
    xpEarned: finish.xp_earned,
    streakDays,
    streakGrew,
    masteryPercent,
    masteryBefore: beforePercent,
    masteryDelta,
    toRepeat: Math.max(0, finish.question_count - finish.correct_count),
    nextSize: after && after.status === "ready" ? after.size : null,
    nextTopic: after && after.status === "ready" ? after.topic : null,
  };
}
