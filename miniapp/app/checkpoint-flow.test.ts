import { describe, expect, it } from "vitest";

import {
  sessionSpendsLives,
  trainerInitialState,
  trainerReducer,
  type TrainerStartResponse,
  type TrainerState,
} from "./trainer-model";
import type { CheckpointRecordResponse, Question } from "./types";

const question: Question = {
  id: "q1",
  type: "single",
  topic: "A",
  title: "t",
  prompt: "p",
  options: [{ id: "o1", label: "one" }, { id: "o2", label: "two" }],
};

function checkpointStart(overrides: Partial<TrainerStartResponse> = {}): TrainerStartResponse {
  return {
    trainer_session_id: "cp-1",
    diagnostic_id: "oge-physics-197",
    content_version: "v1",
    mode: "checkpoint",
    question_ids: ["q1"],
    current_index: 0,
    revision: 1,
    status: "active",
    questions: [question],
    lives_remaining: 0,
    unit_index: 0,
    ...overrides,
  };
}

function record(overrides: Partial<CheckpointRecordResponse> = {}): CheckpointRecordResponse {
  return { ok: true, passed: true, unit_index: 0, mastered_count: 3, question_total: 5, checkpoint: null, checkpoints: [], ...overrides };
}

describe("checkpoint trainer flow", () => {
  it("marks checkpoint and mistakes as lives-free, others as lives-spending", () => {
    expect(sessionSpendsLives("checkpoint")).toBe(false);
    expect(sessionSpendsLives("mistakes")).toBe(false);
    expect(sessionSpendsLives("normal")).toBe(true);
    expect(sessionSpendsLives("today")).toBe(true);
    expect(sessionSpendsLives("plan")).toBe(true);
  });

  it("lets a checkpoint answer submit with no lives left", () => {
    const started = trainerReducer(trainerInitialState, { type: "start", response: checkpointStart() });
    const drafted = trainerReducer(started, { type: "set_answer", answer: "one" });
    const submitted = trainerReducer(drafted, { type: "submit_answer" });
    expect(submitted.phase).toBe("awaiting_result");
    expect(submitted.submittedAnswer).toBe("one");
  });

  it("still blocks a normal answer with no lives left", () => {
    const started = trainerReducer(trainerInitialState, { type: "start", response: checkpointStart({ mode: "normal", unit_index: undefined }) });
    const drafted = trainerReducer(started, { type: "set_answer", answer: "one" });
    const submitted = trainerReducer(drafted, { type: "submit_answer" });
    expect(submitted.phase).toBe("answering");
  });

  it("completes on a checkpoint_result for the matching unit and stores the record", () => {
    const finishing: TrainerState = { ...trainerReducer(trainerInitialState, { type: "start", response: checkpointStart() }), phase: "finishing" };
    const done = trainerReducer(finishing, { type: "checkpoint_result", response: record() });
    expect(done.phase).toBe("completed");
    expect(done.checkpointResult?.passed).toBe(true);
    expect(done.checkpointResult?.mastered_count).toBe(3);
  });

  it("ignores a checkpoint_result for a different unit", () => {
    const finishing: TrainerState = { ...trainerReducer(trainerInitialState, { type: "start", response: checkpointStart({ unit_index: 0 }) }), phase: "finishing" };
    const done = trainerReducer(finishing, { type: "checkpoint_result", response: record({ unit_index: 3 }) });
    expect(done.phase).toBe("finishing");
    expect(done.checkpointResult).toBeNull();
  });
});
