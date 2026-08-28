import type { AnswerValue, Question } from "./types";
import { isValidNumericInput } from "./answer-values";

export type TrainerStartResponse = {
  trainer_session_id: string;
  diagnostic_id: string;
  content_version: string;
  mode: TrainerMode;
  source_attempt_id?: string | null;
  question_ids: string[];
  current_index: number;
  revision: number;
  status: "active" | "in_progress" | "exhausted" | "completed";
  questions: Question[];
  lives_remaining: number;
  next_life_at?: string | null;
};

export type TrainerMode = "normal" | "mistakes";

export type TrainerAnswerResponse = {
  trainer_session_id: string;
  question_id: string;
  is_correct: boolean;
  correct_answer: string | null;
  explanation: string | null;
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
};

export type TrainerAction =
  | { type: "reset" }
  | { type: "start"; response: TrainerStartResponse }
  | { type: "set_answer"; answer: AnswerValue }
  | { type: "submit_answer" }
  | { type: "answer_result"; response: TrainerAnswerResponse }
  | { type: "next_question" }
  | { type: "finish_requested" }
  | { type: "finish_result"; response: TrainerFinishResponse }
  | { type: "error"; message: string }
  | { type: "retry" };

function currentQuestion(state: TrainerState): Question | null {
  return state.session?.questions[state.currentIndex] ?? null;
}

export function isTrainerAnswerComplete(question: Question, answer: AnswerValue | undefined): boolean {
  if (question.type === "single") return typeof answer === "string" && answer.length > 0;
  if (question.type === "multiple") return Array.isArray(answer) && answer.length === question.selection_limit;
  if (question.type === "matching") {
    return Boolean(answer && !Array.isArray(answer) && typeof answer === "object"
      && question.items.every((item) => Boolean(answer[item.id])));
  }
  return isValidNumericInput(answer);
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
      return state.phase === "answering" ? { ...state, draftAnswer: action.answer } : state;
    case "submit_answer":
      return state.phase === "answering" && state.session
        && (state.session.mode === "mistakes" || state.session.lives_remaining > 0)
        && isTrainerAnswerComplete(currentQuestion(state)!, state.draftAnswer)
        ? {
          ...state,
          phase: "awaiting_result",
          answeredQuestionIndex: state.currentIndex,
          submittedAnswer: state.draftAnswer,
          error: null,
        }
        : state;
    case "answer_result":
      if (!state.session || state.phase !== "awaiting_result" || action.response.trainer_session_id !== state.session.trainer_session_id) return state;
      if (action.response.question_id !== state.session.question_ids[state.answeredQuestionIndex ?? state.currentIndex]) return state;
      if (action.response.revision <= state.session.revision) return state;
      return {
        ...state,
        phase: "feedback",
        currentIndex: action.response.current_index,
        answeredQuestionIndex: state.currentIndex,
        answerResult: action.response,
        error: null,
        session: { ...state.session, revision: action.response.revision, status: action.response.status, lives_remaining: action.response.lives_remaining, next_life_at: action.response.next_life_at ?? null },
      };
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
