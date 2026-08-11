export type DiagnosticMode = "quick" | "full";
export type QuestionType = "single" | "multiple" | "matching" | "input";

export type QuestionOption = {
  id: string;
  label: string;
};

type BaseQuestion = {
  id: string;
  type: QuestionType;
  topic: string;
  title: string;
  prompt: string;
  asset?: string;
  assets?: string[];
};

export type SingleQuestion = BaseQuestion & {
  type: "single";
  options: QuestionOption[];
};

export type MultipleQuestion = BaseQuestion & {
  type: "multiple";
  options: QuestionOption[];
  selection_limit: number;
};

export type MatchingQuestion = BaseQuestion & {
  type: "matching";
  items: QuestionOption[];
  options: QuestionOption[];
};

export type InputQuestion = BaseQuestion & {
  type: "input";
};

export type Question =
  | SingleQuestion
  | MultipleQuestion
  | MatchingQuestion
  | InputQuestion;

export type AnswerValue = string | string[] | Record<string, string>;
export type AnswerMap = Record<string, AnswerValue>;

export type PublicDiagnostic = {
  id: string;
  content_version: string;
  exam: string;
  subject: string;
  mark: string;
  quick_count: number;
  questions: Question[];
};

export type Brand = {
  school_id: string;
  name: string;
  short_name: string;
  colors: {
    primary: string;
    accent: string;
    background: string;
    signal: string;
    ink: string;
    paper: string;
  };
  logo: string;
  interface: {
    command_start: string;
    command_diagnostics: string;
    command_results: string;
    command_plan: string;
    start_diagnostic: string;
    open_diagnostic: string;
    results: string;
    plan: string;
    home: string;
    take_full_diagnostic: string;
    check_another_subject: string;
    take_another_diagnostic: string;
    quick_result: string;
    full_result: string;
    ready_result: string;
    unassessed_full: string;
    results_heading: string;
    diagnostic_fallback: string;
    plan_for: string;
    keep_strong: string;
    focus_next: string;
    open_result_hint: string;
    result_not_found: string;
    back: string;
    task_label: string;
    of_label: string;
    answer_label: string;
    enter_answer: string;
    choose_option: string;
    next_question: string;
    get_result: string;
    result_in_telegram: string;
    privacy_label: string;
    support_label: string;
    choose_label: string;
    close_diagnostic: string;
    illustration_alt: string;
    result_score: string;
    result_correct: string;
    delivery_note: string;
  };
};

export type SchoolLinks = {
  website: string;
  support: string;
  privacy: string;
  offers: Array<{
    id: string;
    label: string;
    button: string;
    url: string;
  }>;
};

export type ServerTopic = {
  topic: string;
  question_count?: number;
  correct_count?: number;
  ratio?: number;
};

export type ForecastPoint = {
  id: string;
  label: string;
  value: number;
};

export type ServerResult = {
  diagnostic_id: string;
  mode: DiagnosticMode;
  question_count: number;
  correct_count: number;
  score: number;
  max_score: number;
  score_unit: string;
  unassessed_part?: string | null;
  strong_topics: Array<ServerTopic | string>;
  growth_topics: Array<ServerTopic | string>;
  forecast?: { points: ForecastPoint[] } | Record<string, number>;
};

export type ServerAttempt = {
  attempt_id: string;
  diagnostic_id: string;
  content_version: string;
  mode: DiagnosticMode;
  status: "in_progress" | "completed";
  question_index: number;
  question_count: number;
  progress_revision: number;
  answers: AnswerMap;
};

export type BootstrapResponse = {
  session_scope: string;
  latest_attempt_id: string | null;
  school: {
    brand: Brand;
    links: SchoolLinks;
  };
  diagnostics: PublicDiagnostic[];
  attempt: ServerAttempt | null;
  results: ServerAttempt[];
};

export type CompletionResponse = {
  ok: true;
  attempt: ServerAttempt;
  result: ServerResult;
};

export type ReviewItem = {
  question_id: string;
  number: number;
  type: QuestionType;
  topic: string;
  title: string;
  prompt: string;
  asset?: string;
  assets?: string[];
  is_correct: boolean;
  user_answer: string;
  expected_answer: string;
  guidance: string;
  guidance_kind: "individual" | "fallback";
};

export type ReviewResponse = {
  ok: true;
  available: boolean;
  items: ReviewItem[];
  pdf_status: "pending" | "sending" | "sent" | "failed" | "abandoned";
};

export type SavedSession = {
  attemptId: string;
  supersedesAttemptId?: string;
  diagnosticId: string;
  contentVersion: string;
  mode: DiagnosticMode;
  questionIndex: number;
  revision: number;
  answers: AnswerMap;
  syncedQuestionIndex?: number;
  syncedAnswers?: AnswerMap;
};
