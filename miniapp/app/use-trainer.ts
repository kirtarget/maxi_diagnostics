"use client";

import { useCallback, useReducer, useRef, useState, type Dispatch } from "react";

import { answerTrainer, apiErrorDetail, finishTrainer, recordCheckpoint, requestLivesReminder, startCheckpoint, startTrainer } from "./api";
import type { LivesReminderState } from "./trainer-screen";
import {
  trainerInitialState,
  trainerReducer,
  type TrainerAction,
  type TrainerMode,
  type TrainerState,
} from "./trainer-model";
import type { AnswerValue, BootstrapResponse, Screen } from "./types";

/** Server error details that only a fresh trainer session can recover from. */
const RESTART_ON_ANSWER = new Set([
  "trainer_revision_stale",
  "trainer_answer_conflict",
  "trainer_question_out_of_order",
  "trainer_content_changed",
  "trainer_session_not_found",
  "trainer_session_not_active",
]);
const RESTART_ON_FINISH = new Set([
  "trainer_revision_stale",
  "trainer_session_not_found",
  "trainer_content_changed",
]);

export type TrainerSessionState = {
  trainer: TrainerState;
  livesReminder: LivesReminderState;
};

export type TrainerActions = {
  dispatch: Dispatch<TrainerAction>;
  start(diagnosticId: string, mode?: TrainerMode, sourceAttemptId?: string, topic?: string, count?: number): Promise<void>;
  /** Start the weekly checkpoint for one unit. Runs the same trainer cycle, records a unit pass on finish. */
  startCheckpoint(diagnosticId: string, contentVersion: string, unitIndex: number): Promise<void>;
  answer(questionId: string, answer: AnswerValue, giveUp?: boolean): Promise<void>;
  finish(): Promise<void>;
  remindLives(): Promise<void>;
  retry(): void;
};

export type TrainerSession = {
  state: TrainerSessionState;
  actions: TrainerActions;
};

export function trainerErrorMessage(error: unknown): string {
  switch (apiErrorDetail(error)) {
    case "trainer_no_lives": return "Жизни закончились. Ответить сейчас нельзя, попробуй позже.";
    case "trainer_revision_stale":
    case "trainer_answer_conflict":
    case "trainer_question_out_of_order": return "Сессия устарела. Запусти тренировку заново.";
    case "trainer_content_changed": return "Материалы обновились. Запусти новую тренировку.";
    case "trainer_session_not_found":
    case "trainer_session_not_active": return "Эта тренировка больше недоступна. Запусти новую.";
    case "trainer_session_incomplete": return "Сначала ответь на все вопросы.";
    case "session_expired": return "Сессия Telegram устарела. Перезагрузи приложение.";
    case "trainer_not_enough_questions": return "Для тренировки пока недостаточно заданий.";
    case "trainer_no_mistakes": return "В этой диагностике нет ошибок для тренировки.";
    case "trainer_mistakes_source_not_found": return "Результат диагностики больше недоступен для тренировки.";
    case "trainer_mistakes_source_conflict": return "Результат уже используется в другой тренировке. Открой его снова и повтори попытку.";
    case "trainer_plan_unavailable":
    case "trainer_plan_conflict": return "План на сегодня пока не готов. Пройди диагностику.";
    default: return "Не удалось связаться с сервером. Повтори попытку.";
  }
}

export function useTrainer({
  bootstrap,
  initData,
  sessionScope,
  setScreen,
  refreshProgress,
}: {
  bootstrap: BootstrapResponse | null;
  initData: { current: string };
  sessionScope: string | undefined;
  setScreen: (screen: Screen) => void;
  refreshProgress?: () => Promise<void>;
}): TrainerSession {
  const [trainer, dispatch] = useReducer(trainerReducer, trainerInitialState);
  const [livesReminder, setLivesReminder] = useState<LivesReminderState>({ status: "idle" });
  const diagnosticId = useRef<string | null>(null);
  const mode = useRef<TrainerMode>("normal");
  const sourceAttemptId = useRef<string | null>(null);
  const topic = useRef<string | null>(null);
  const count = useRef<number | undefined>(undefined);
  const contentVersion = useRef<string | null>(null);
  const unitIndex = useRef<number | null>(null);
  const requestGeneration = useRef(0);
  const recoveryMode = useRef<"retry" | "restart">("retry");
  /** Guards the checkpoint record POST against the double finish call the screen makes. */
  const recordedCheckpointKey = useRef<string | null>(null);

  const start = useCallback(async (
    selectedId: string,
    requestedMode: TrainerMode = "normal",
    requestedSourceAttemptId?: string,
    requestedTopic?: string,
    requestedCount?: number,
  ) => {
    if (!sessionScope || !initData.current) return;
    const selected = bootstrap?.diagnostics.find((item) => item.id === selectedId);
    if (!selected) {
      dispatch({ type: "error", message: "Диагностика для тренировки не найдена." });
      return;
    }
    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    diagnosticId.current = selected.id;
    mode.current = requestedMode;
    sourceAttemptId.current = requestedMode === "mistakes" ? (requestedSourceAttemptId ?? null) : null;
    topic.current = requestedMode === "mistakes" ? (requestedTopic ?? null) : null;
    count.current = requestedCount;
    recoveryMode.current = "retry";
    dispatch({ type: "reset" });
    setLivesReminder({ status: "idle" });
    setScreen("trainer");
    try {
      const requested = requestedCount && requestedCount > 0 ? requestedCount : 5;
      const scope = {
        session_scope: sessionScope,
        diagnostic_id: selected.id,
        count: Math.min(requested, selected.question_count),
      };
      const payload = requestedMode === "mistakes" && requestedSourceAttemptId
        ? { ...scope, mode: "mistakes" as const, source_attempt_id: requestedSourceAttemptId, ...(requestedTopic ? { topic: requestedTopic } : {}) }
        : requestedMode === "plan"
          ? { ...scope, mode: "plan" as const }
          : requestedMode === "today"
            ? { ...scope, mode: "today" as const }
            : { ...scope, mode: "normal" as const };
      const response = await startTrainer(initData.current, payload);
      if (generation !== requestGeneration.current) return;
      dispatch({ type: "start", response });
    } catch (startError) {
      if (generation !== requestGeneration.current) return;
      dispatch({ type: "error", message: trainerErrorMessage(startError) });
    }
  }, [bootstrap, initData, sessionScope, setScreen]);

  const startCheckpointSession = useCallback(async (
    selectedId: string,
    selectedContentVersion: string,
    selectedUnitIndex: number,
  ) => {
    if (!sessionScope || !initData.current) return;
    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    diagnosticId.current = selectedId;
    mode.current = "checkpoint";
    sourceAttemptId.current = null;
    topic.current = null;
    count.current = undefined;
    contentVersion.current = selectedContentVersion;
    unitIndex.current = selectedUnitIndex;
    recordedCheckpointKey.current = null;
    recoveryMode.current = "retry";
    dispatch({ type: "reset" });
    setLivesReminder({ status: "idle" });
    setScreen("trainer");
    try {
      const response = await startCheckpoint(initData.current, {
        session_scope: sessionScope,
        diagnostic_id: selectedId,
        content_version: selectedContentVersion,
        unit_index: selectedUnitIndex,
      });
      if (generation !== requestGeneration.current) return;
      dispatch({ type: "start", response });
    } catch (startError) {
      if (generation !== requestGeneration.current) return;
      dispatch({ type: "error", message: trainerErrorMessage(startError) });
    }
  }, [initData, sessionScope, setScreen]);

  const answer = useCallback(async (questionId: string, value: AnswerValue, giveUp = false) => {
    const session = trainer.session;
    if (!session || !sessionScope || !initData.current) return;
    try {
      const response = await answerTrainer(initData.current, {
        session_scope: sessionScope,
        trainer_session_id: session.trainer_session_id,
        question_id: questionId,
        answer: value ?? null,
        revision: session.revision,
        idempotency_key: `trainer-answer-${session.trainer_session_id}-${questionId}-${session.revision}`,
        ...(giveUp ? { give_up: true } : {}),
      });
      dispatch({ type: "answer_result", response });
      void refreshProgress?.();
    } catch (answerError) {
      if (RESTART_ON_ANSWER.has(apiErrorDetail(answerError) ?? "")) {
        recoveryMode.current = "restart";
      }
      dispatch({ type: "error", message: trainerErrorMessage(answerError) });
    }
  }, [initData, sessionScope, trainer.session, refreshProgress]);

  const finish = useCallback(async () => {
    const session = trainer.session;
    if (!session || !sessionScope || !initData.current) return;
    if (mode.current === "checkpoint" && unitIndex.current !== null) {
      // The screen calls finish twice for one tap (explicit plus auto-finish
      // effect); a checkpoint record mutates unit state, so run it once per session.
      const recordKey = session.trainer_session_id;
      if (recordedCheckpointKey.current === recordKey) return;
      recordedCheckpointKey.current = recordKey;
      try {
        const response = await recordCheckpoint(initData.current, {
          session_scope: sessionScope,
          trainer_session_id: session.trainer_session_id,
          unit_index: unitIndex.current,
          revision: session.revision,
        });
        dispatch({ type: "checkpoint_result", response });
        void refreshProgress?.();
      } catch (recordError) {
        recordedCheckpointKey.current = null;
        if (RESTART_ON_FINISH.has(apiErrorDetail(recordError) ?? "")) {
          recoveryMode.current = "restart";
        }
        dispatch({ type: "error", message: trainerErrorMessage(recordError) });
      }
      return;
    }
    try {
      const response = await finishTrainer(initData.current, {
        session_scope: sessionScope,
        trainer_session_id: session.trainer_session_id,
        revision: session.revision,
      });
      dispatch({ type: "finish_result", response });
      void refreshProgress?.();
    } catch (finishError) {
      if (RESTART_ON_FINISH.has(apiErrorDetail(finishError) ?? "")) {
        recoveryMode.current = "restart";
      }
      dispatch({ type: "error", message: trainerErrorMessage(finishError) });
    }
  }, [initData, sessionScope, trainer.session, refreshProgress]);

  const remindLives = useCallback(async () => {
    if (!sessionScope || !initData.current) return;
    setLivesReminder({ status: "pending" });
    try {
      await requestLivesReminder(initData.current, sessionScope);
      setLivesReminder({ status: "scheduled" });
    } catch {
      setLivesReminder({ status: "error" });
    }
  }, [initData, sessionScope]);

  const retry = useCallback(() => {
    const restart = () => {
      if (mode.current === "checkpoint" && diagnosticId.current && contentVersion.current !== null && unitIndex.current !== null) {
        void startCheckpointSession(diagnosticId.current, contentVersion.current, unitIndex.current);
        return;
      }
      if (diagnosticId.current) {
        void start(diagnosticId.current, mode.current, sourceAttemptId.current ?? undefined, topic.current ?? undefined, count.current);
      }
    };
    if (recoveryMode.current === "restart" && diagnosticId.current) {
      restart();
      return;
    }
    if (trainer.retryPhase === "idle" && diagnosticId.current) {
      restart();
      return;
    }
    if (trainer.retryPhase === "finishing") {
      void finish();
      return;
    }
    const session = trainer.session;
    const questionIndex = trainer.answeredQuestionIndex;
    const submitted = trainer.submittedAnswer;
    const questionId = questionIndex === null ? null : session?.question_ids[questionIndex];
    if (!session || !questionId || submitted === undefined) {
      restart();
      return;
    }
    void answer(questionId, submitted);
  }, [answer, finish, start, startCheckpointSession, trainer]);

  return {
    state: { trainer, livesReminder },
    actions: { dispatch, start, startCheckpoint: startCheckpointSession, answer, finish, remindLives, retry },
  };
}
