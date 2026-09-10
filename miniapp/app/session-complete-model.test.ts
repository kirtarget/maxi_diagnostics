import { describe, expect, it } from "vitest";

import { sessionCompleteView, type SessionStartSnapshot } from "./session-complete-model";
import type { TrainerFinishResponse } from "./trainer-model";
import type { TodaySession, TopicPathNode } from "./types";

const finish: TrainerFinishResponse = {
  trainer_session_id: "s1",
  status: "completed",
  revision: 6,
  current_index: 5,
  question_count: 5,
  answered_count: 5,
  correct_count: 3,
  xp_earned: 40,
  lives_spent: 2,
  lives_remaining: 3,
};

function pathNode(topic: string, mastered: number, total: number, status: TopicPathNode["status"]): TopicPathNode {
  return { topic, index: 0, total, mastered, status, done_at: null };
}

function today(overrides: Partial<TodaySession>): TodaySession {
  return {
    status: "ready",
    diagnostic_id: "phys",
    content_version: "v1",
    subject: "Физика",
    exam: "ОГЭ",
    topic: "Тепловые явления",
    topic_total: 12,
    topic_mastered: 7,
    size: 5,
    estimated_minutes: 4,
    streak_days: 5,
    daily_goal: { date: "2026-09-11", target: 1, progress: 1, complete: true },
    xp_total: 320,
    path: [pathNode("Тепловые явления", 7, 12, "current")],
    ...overrides,
  };
}

describe("sessionCompleteView", () => {
  const before: SessionStartSnapshot = { topic: "Тепловые явления", mastered: 5, total: 12, streakDays: 4 };

  it("reports the session tally as a count, not an accuracy percent", () => {
    const view = sessionCompleteView(finish, before, today({}));
    expect(view.solved).toBe(3);
    expect(view.size).toBe(5);
    expect(view.answered).toBe(5);
    expect(view.xpEarned).toBe(40);
  });

  it("computes topic-mastery growth from the before and after snapshots", () => {
    const after = today({ topic_mastered: 7, path: [pathNode("Тепловые явления", 7, 12, "current")] });
    const view = sessionCompleteView(finish, before, after);
    expect(view.masteryBefore).toBe(42);
    expect(view.masteryPercent).toBe(58);
    expect(view.masteryDelta).toBe(16);
  });

  it("marks the streak as grown only when the after streak is higher", () => {
    expect(sessionCompleteView(finish, before, today({ streak_days: 5 })).streakGrew).toBe(true);
    expect(sessionCompleteView(finish, before, today({ streak_days: 4 })).streakGrew).toBe(false);
    expect(sessionCompleteView(finish, before, today({ streak_days: 5 })).streakDays).toBe(5);
  });

  it("counts questions still to repeat and surfaces tomorrow when ready", () => {
    const after = today({ size: 5, topic: "Тепловые явления" });
    const view = sessionCompleteView(finish, before, after);
    expect(view.toRepeat).toBe(2);
    expect(view.nextSize).toBe(5);
    expect(view.nextTopic).toBe("Тепловые явления");
  });

  it("hides tomorrow when the path is complete", () => {
    const after = today({ status: "path_complete", topic: null });
    const view = sessionCompleteView(finish, before, after);
    expect(view.nextSize).toBeNull();
    expect(view.nextTopic).toBeNull();
  });

  it("degrades gracefully when no after snapshot is available", () => {
    const view = sessionCompleteView(finish, before, null);
    expect(view.masteryBefore).toBe(42);
    expect(view.masteryPercent).toBe(42);
    expect(view.masteryDelta).toBe(0);
    expect(view.streakGrew).toBe(false);
    expect(view.streakDays).toBe(4);
  });
});
