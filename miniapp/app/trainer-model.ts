import type { AnswerValue, BootstrapResponse, PlanReason, Question } from "./types";
import { answerReadiness } from "./answer-readiness";
import { lifeNote } from "./trainer-feedback";

/** Plan context the server attaches when a session runs today's plan. */
export type TrainerPlanInfo = {
  plan_date: string;
  total: number;
  completed: number;
  reasons: Partial<Record<string, PlanReason>>;
};

export type TrainerStartResponse = {
  trainer_session_id: string;
  diagnostic_id: string;
  content_version: string;
  mode: TrainerMode;
  source_attempt_id?: string | null;
  topic?: string | null;
  question_ids: string[];
  current_index: number;
  revision: number;
  status: "active" | "in_progress" | "exhausted" | "completed";
  questions: Question[];
  lives_remaining: number;
  next_life_at?: string | null;
  plan?: TrainerPlanInfo | null;
};

export type TrainerMode = "normal" | "mistakes" | "plan" | "today";

export type TrainerHeaderView = {
  diagnosticId: string;
  exam: string;
  subject: string;
  mode: TrainerMode;
  modeLabel: string;
};

export type TrainerSessionIdentity = Pick<TrainerStartResponse, "diagnostic_id" | "mode" | "topic">;

export type TrainerFeedbackKind = "correct" | "partial" | "incorrect";

export const TRAINER_MODE_LABELS: Record<TrainerMode, string> = {
  normal: "Тренировка",
  mistakes: "Повтор ошибок",
  plan: "План на сегодня",
  today: "Сегодняшняя сессия",
};

export function trainerModeLabel(mode: TrainerMode): string {
  return TRAINER_MODE_LABELS[mode];
}

function completedAttemptDiagnosticId(attempt: BootstrapResponse["results"][number] | null | undefined): string | null {
  return attempt?.status === "completed" && attempt.diagnostic_id ? attempt.diagnostic_id : null;
}

export function trainerDiagnosticId(
  bootstrap: BootstrapResponse | null | undefined,
  subjectChoice?: string | null,
): string | null {
  if (!bootstrap) return null;
  if (bootstrap.attempt?.status === "in_progress" && bootstrap.attempt.diagnostic_id) {
    return bootstrap.attempt.diagnostic_id;
  }
  if (bootstrap.daily_plan?.diagnostic_id) return bootstrap.daily_plan.diagnostic_id;

  const latest = bootstrap.latest_attempt_id
    ? bootstrap.results.find((attempt) => attempt.attempt_id === bootstrap.latest_attempt_id)
    : null;
  const latestDiagnosticId = completedAttemptDiagnosticId(latest);
  if (latestDiagnosticId) return latestDiagnosticId;

  const firstCompleted = bootstrap.results.map(completedAttemptDiagnosticId).find((diagnosticId): diagnosticId is string => diagnosticId !== null);
  if (firstCompleted) return firstCompleted;

  if (subjectChoice) return bootstrap.diagnostics.find((diagnostic) => diagnostic.subject === subjectChoice)?.id ?? null;
  return null;
}

export function trainerHeaderView(
  bootstrap: BootstrapResponse | null | undefined,
  session: TrainerSessionIdentity | null | undefined,
): TrainerHeaderView | null {
  if (!session) return null;
  const diagnostic = bootstrap?.diagnostics.find((candidate) => candidate.id === session.diagnostic_id);
  if (!diagnostic) return null;
  return {
    diagnosticId: diagnostic.id,
    exam: diagnostic.exam,
    subject: diagnostic.subject,
    mode: session.mode,
    modeLabel: trainerModeLabel(session.mode),
  };
}

export function trainerFeedbackKind(result: Pick<TrainerAnswerResponse, "is_correct" | "earned_primary_score" | "max_primary_score">): TrainerFeedbackKind {
  if (result.is_correct) return "correct";
  const earned = result.earned_primary_score;
  const maximum = result.max_primary_score;
  return typeof earned === "number" && typeof maximum === "number" && earned > 0 && earned < maximum
    ? "partial"
    : "incorrect";
}

export const PLAN_REASON_LABELS: Record<PlanReason, string> = {
  mistake_review: "повтор ошибки",
  growth_topic: "зона роста",
};

/** Answered plan questions counted from the session, so the tag updates as you go. */
export function planProgress(state: TrainerState): { completed: number; total: number } | null {
  const session = state.session;
  if (!session || session.mode !== "plan" || !session.plan) return null;
  const answered = Math.max(state.currentIndex, session.plan.completed);
  return { completed: Math.min(answered, session.plan.total), total: session.plan.total };
}

export function planReasonLabel(state: TrainerState, questionId: string): string | null {
  const reason = state.session?.plan?.reasons[questionId];
  return reason ? PLAN_REASON_LABELS[reason] : null;
}

export type TrainerAnswerResponse = {
  trainer_session_id: string;
  question_id: string;
  is_correct: boolean;
  correct_answer: string | null;
  explanation: string | null;
  max_primary_score?: number;
  earned_primary_score?: number;
  xp_delta: number;
  life_delta: number;
  current_index: number;
  revision: number;
  status: "active" | "in_progress" | "exhausted" | "completed";
  lives_remaining: number;
  next_life_at?: string | null;
};

export type TrainerFinishResponse = {
  trainer_session_id: string;
  status: "completed";
  revision: number;
  current_index: number;
  question_count: number;
  answered_count: number;
  correct_count: number;
  xp_earned: number;
  lives_spent: number;
  lives_remaining: number;
};

export type TrainerPhase = "idle" | "answering" | "awaiting_result" | "feedback" | "finishing" | "completed" | "error";

export type TrainerState = {
  phase: TrainerPhase;
  session: TrainerStartResponse | null;
  currentIndex: number;
  answeredQuestionIndex: number | null;
  draftAnswer: AnswerValue | undefined;
  submittedAnswer: AnswerValue | undefined;
  answerResult: TrainerAnswerResponse | null;
  finishResult: TrainerFinishResponse | null;
  error: string | null;
  retryPhase: Exclude<TrainerPhase, "error"> | null;
  /** Set while a give-up request is in flight, so its result knows where to land. */
  giveUp: TrainerGiveUp | null;
  /** Carried onto the next question when a skip spends a life without a feedback panel. */
  notice: string | null;
};

export const trainerInitialState: TrainerState = {
  phase: "idle",
  session: null,
  currentIndex: 0,
  answeredQuestionIndex: null,
  draftAnswer: undefined,
  submittedAnswer: undefined,
  answerResult: null,
  finishResult: null,
  error: null,
  retryPhase: null,
  giveUp: null,
  notice: null,
};

/** Reveal keeps the student on the question; skip carries them to the next one. */
export type TrainerGiveUp = "reveal" | "skip";

export type TrainerAction =
  | { type: "reset" }
  | { type: "start"; response: TrainerStartResponse }
  | { type: "set_answer"; answer: AnswerValue }
  | { type: "submit_answer" }
  | { type: "give_up"; intent: TrainerGiveUp }
  | { type: "answer_result"; response: TrainerAnswerResponse }
  | { type: "next_question" }
  | { type: "finish_requested" }
  | { type: "finish_result"; response: TrainerFinishResponse }
  | { type: "error"; message: string }
  | { type: "retry" };

function currentQuestion(state: TrainerState): Question | null {
  return state.session?.questions[state.currentIndex] ?? null;
}

/**
 * The trainer submits exactly what the question screen would let through, so the
 * guard reads the same readiness the action bar explains.
 */
export function isTrainerAnswerComplete(question: Question, answer: AnswerValue | undefined, subject?: string): boolean {
  return answerReadiness(question, answer, subject).isAnswered;
}

export function trainerReducer(state: TrainerState, action: TrainerAction): TrainerState {
  switch (action.type) {
    case "reset":
      return trainerInitialState;
    case "start":
      return {
        ...trainerInitialState,
        phase: action.response.status === "completed" ? "completed" : action.response.status === "exhausted" ? "finishing" : "answering",
        session: action.response,
        currentIndex: action.response.current_index,
        answeredQuestionIndex: null,
      };
    case "set_answer":
      return state.phase === "answering" ? { ...state, draftAnswer: action.answer, notice: null } : state;
    case "give_up":
      // Unlike a submission this needs no complete answer: not knowing one is the point.
      return state.phase === "answering" && state.session
        && (state.session.mode === "mistakes" || state.session.lives_remaining > 0)
        ? {
          ...state,
          phase: "awaiting_result",
          answeredQuestionIndex: state.currentIndex,
          submittedAnswer: state.draftAnswer,
          giveUp: action.intent,
          notice: null,
          error: null,
        }
        : state;
    case "submit_answer":
      return state.phase === "answering" && state.session
        && (state.session.mode === "mistakes" || state.session.lives_remaining > 0)
        && isTrainerAnswerComplete(currentQuestion(state)!, state.draftAnswer)
        ? {
          ...state,
          phase: "awaiting_result",
          answeredQuestionIndex: state.currentIndex,
          submittedAnswer: state.draftAnswer,
          giveUp: null,
          notice: null,
          error: null,
        }
        : state;
    case "answer_result":
      if (!state.session || state.phase !== "awaiting_result" || action.response.trainer_session_id !== state.session.trainer_session_id) return state;
      if (action.response.question_id !== state.session.question_ids[state.answeredQuestionIndex ?? state.currentIndex]) return state;
      if (action.response.revision <= state.session.revision) return state;
      {
        const session = { ...state.session, revision: action.response.revision, status: action.response.status, lives_remaining: action.response.lives_remaining, next_life_at: action.response.next_life_at ?? null };
        const nextIndex = action.response.current_index;
        const skipped = state.giveUp === "skip"
          && ["active", "in_progress"].includes(action.response.status)
          && nextIndex >= 0 && nextIndex < state.session.questions.length;
        // A skip shows no feedback panel, so the life it spent has to be announced
        // on the question the student lands on instead.
        if (skipped) {
          const life = lifeNote(action.response, session.mode);
          return {
            ...state,
            phase: "answering",
            currentIndex: nextIndex,
            answeredQuestionIndex: null,
            draftAnswer: undefined,
            submittedAnswer: undefined,
            answerResult: null,
            giveUp: null,
            notice: life ? `Вопрос пропущен. ${life.text}` : "Вопрос пропущен.",
            error: null,
            session,
          };
        }
        return {
          ...state,
          phase: "feedback",
          currentIndex: nextIndex,
          answeredQuestionIndex: state.currentIndex,
          answerResult: action.response,
          giveUp: null,
          notice: null,
          error: null,
          session,
        };
      }
    case "next_question": {
      const result = state.answerResult;
      if (!state.session || state.phase !== "feedback" || !result || !["active", "in_progress"].includes(result.status)) return state;
      const nextIndex = result.current_index;
      return nextIndex < 0 || nextIndex >= state.session.questions.length ? state : {
        ...state,
        phase: "answering",
        currentIndex: nextIndex,
        answeredQuestionIndex: null,
        draftAnswer: undefined,
        submittedAnswer: undefined,
        answerResult: null,
      };
    }
    case "finish_requested":
      return state.phase === "feedback" && state.session !== null
        && state.currentIndex >= state.session.questions.length
        ? { ...state, phase: "finishing", error: null }
        : state;
    case "finish_result":
      return state.session && action.response.trainer_session_id === state.session.trainer_session_id
        ? { ...state, phase: "completed", finishResult: action.response, error: null }
        : state;
    case "error":
      return { ...state, phase: "error", error: action.message, retryPhase: state.phase === "error" ? state.retryPhase : state.phase };
    case "retry":
      return state.phase === "error" && state.retryPhase
        ? { ...state, phase: state.retryPhase, error: null, retryPhase: null }
        : state;
  }
}
