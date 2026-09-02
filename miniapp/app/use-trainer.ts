"use client";

import { useCallback, useReducer, useRef, useState, type Dispatch } from "react";

import { answerTrainer, apiErrorDetail, finishTrainer, requestLivesReminder, startTrainer } from "./api";
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
  start(diagnosticId: string, mode?: TrainerMode, sourceAttemptId?: string): Promise<void>;
  answer(questionId: string, answer: AnswerValue): Promise<void>;
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
    default: return "Не удалось связаться с сервером. Повтори попытку.";
  }
}

export function useTrainer({
  bootstrap,
  initData,
  sessionScope,
  setScreen,
}: {
  bootstrap: BootstrapResponse | null;
  initData: { current: string };
  sessionScope: string | undefined;
  setScreen: (screen: Screen) => void;
}): TrainerSession {
  const [trainer, dispatch] = useReducer(trainerReducer, trainerInitialState);
  const [livesReminder, setLivesReminder] = useState<LivesReminderState>({ status: "idle" });
  const diagnosticId = useRef<string | null>(null);
  const mode = useRef<TrainerMode>("normal");
  const sourceAttemptId = useRef<string | null>(null);
  const recoveryMode = useRef<"retry" | "restart">("retry");

  const start = useCallback(async (
    selectedId: string,
    requestedMode: TrainerMode = "normal",
    requestedSourceAttemptId?: string,
  ) => {
    if (!sessionScope || !initData.current) return;
    const selected = bootstrap?.diagnostics.find((item) => item.id === selectedId);
    if (!selected) {
      dispatch({ type: "error", message: "Диагностика для тренировки не найдена." });
      return;
    }
    diagnosticId.current = selected.id;
    mode.current = requestedMode;
    sourceAttemptId.current = requestedMode === "mistakes" ? (requestedSourceAttemptId ?? null) : null;
    recoveryMode.current = "retry";
    dispatch({ type: "reset" });
    setLivesReminder({ status: "idle" });
    setScreen("trainer");
    try {
      const payload = requestedMode === "mistakes" && requestedSourceAttemptId
        ? {
          session_scope: sessionScope,
          diagnostic_id: selected.id,
          count: Math.min(5, selected.question_count),
          mode: "mistakes" as const,
          source_attempt_id: requestedSourceAttemptId,
        }
        : {
          session_scope: sessionScope,
          diagnostic_id: selected.id,
          count: Math.min(5, selected.question_count),
          mode: "normal" as const,
        };
      const response = await startTrainer(initData.current, payload);
      dispatch({ type: "start", response });
    } catch (startError) {
      dispatch({ type: "error", message: trainerErrorMessage(startError) });
    }
  }, [bootstrap, initData, sessionScope, setScreen]);

  const answer = useCallback(async (questionId: string, value: AnswerValue) => {
    const session = trainer.session;
    if (!session || !sessionScope || !initData.current) return;
    try {
      const response = await answerTrainer(initData.current, {
        session_scope: sessionScope,
        trainer_session_id: session.trainer_session_id,
        question_id: questionId,
        answer: value,
        revision: session.revision,
        idempotency_key: `trainer-answer-${session.trainer_session_id}-${questionId}-${session.revision}`,
      });
      dispatch({ type: "answer_result", response });
    } catch (answerError) {
      if (RESTART_ON_ANSWER.has(apiErrorDetail(answerError) ?? "")) {
        recoveryMode.current = "restart";
      }
      dispatch({ type: "error", message: trainerErrorMessage(answerError) });
    }
  }, [initData, sessionScope, trainer.session]);

  const finish = useCallback(async () => {
    const session = trainer.session;
    if (!session || !sessionScope || !initData.current) return;
    try {
      const response = await finishTrainer(initData.current, {
        session_scope: sessionScope,
        trainer_session_id: session.trainer_session_id,
        revision: session.revision,
      });
      dispatch({ type: "finish_result", response });
    } catch (finishError) {
      if (RESTART_ON_FINISH.has(apiErrorDetail(finishError) ?? "")) {
        recoveryMode.current = "restart";
      }
      dispatch({ type: "error", message: trainerErrorMessage(finishError) });
    }
  }, [initData, sessionScope, trainer.session]);

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
      if (diagnosticId.current) {
        void start(diagnosticId.current, mode.current, sourceAttemptId.current ?? undefined);
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
  }, [answer, finish, start, trainer]);

  return {
    state: { trainer, livesReminder },
    actions: { dispatch, start, answer, finish, remindLives, retry },
  };
}
