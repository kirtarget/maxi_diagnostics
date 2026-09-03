/** Every screen the mini app can show. Owned by `page.tsx`, shared with its hooks. */
export type Screen =
  | "loading"
  | "diagnostic-loading"
  | "welcome"
  | "home"
  | "profile"
  | "league"
  | "mode"
  | "subjects"
  | "question"
  | "submitting"
  | "result"
  | "review"
  | "forecast"
  | "route"
  | "trainer";

export type DiagnosticMode = "quick" | "full";
export type QuestionType = "single" | "multiple" | "matching" | "input" | "text";

export type QuestionOption = {
  id: string;
  label: string;
};

export type QuestionSourceAttribution = {
  provider: string;
  official_year: number;
  approval_status: "approved" | "draft";
  source_kind: "open_bank" | "open_variant" | "demo" | "specification" | "commission_material" | "original";
  source_url: string;
  fipi_project_id?: string;
  fipi_question_id?: string;
  exam_position?: string;
  official_criteria_url?: string;
  rights_status: "link_only" | "written_permission" | "licensed_copy" | "original";
  verified_at: string;
};

type BaseQuestion = {
  id: string;
  type: QuestionType;
  topic: string;
  title: string;
  prompt: string;
  max_primary_score?: number;
  source?: QuestionSourceAttribution;
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

/** Short written answer. The server holds every accepted spelling; `max_length` only sizes the field. */
export type TextQuestion = BaseQuestion & {
  type: "text";
  max_length?: number;
};

export type Question =
  | SingleQuestion
  | MultipleQuestion
  | MatchingQuestion
  | InputQuestion
  | TextQuestion;

export type AnswerValue = string | string[] | Record<string, string>;
export type AnswerMap = Record<string, AnswerValue>;

export type PublicDiagnosticSummary = {
  id: string;
  content_version: string;
  exam: string;
  subject: string;
  mark: string;
  quick_count: number;
  question_count: number;
};

export type PublicDiagnostic = PublicDiagnosticSummary & {
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

export type ForecastKind = "test_score" | "grade" | "accuracy_percent";

/** Server-computed estimate of the exam result this sample points to. */
export type ScoreEstimate = {
  kind: "test_score" | "grade";
  value: number;
  scaled_primary: number;
  exam_max_primary: number;
  sample_max_primary: number;
  sample_size: number;
  min_pass: number | null;
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
  recoverable_primary_score?: number;
  estimate?: ScoreEstimate | null;
  forecast?: { kind?: ForecastKind; points: ForecastPoint[] } | Record<string, number>;
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
  estimate?: ScoreEstimate | null;
};

export type ProgressProfile = {
  completion_count: number;
  achievement_keys: string[];
};

export type GameplayDailyGoal = {
  date: string | null;
  target: number;
  progress: number;
  complete: boolean;
};

export type GameplayQuest = {
  key: string;
  date: string | null;
  target: number;
  progress: number;
};

export type GameplayProfile = {
  xp_total: number;
  level: number;
  level_progress: number;
  streak_days: number;
  lives_remaining: number;
  next_life_at?: string | null;
  daily_goal: GameplayDailyGoal;
  quest: GameplayQuest | null;
};

/** Why the server put one question in today's plan. */
export type PlanReason = "mistake_review" | "growth_topic";

export type PlanStatus = "ready" | "done" | "no_diagnostic";

/** Compact plan progress carried by `/bootstrap` so the home screen needs no extra call. */
export type DailyPlanSummary = {
  plan_date: string | null;
  diagnostic_id: string | null;
  subject: string | null;
  exam: string | null;
  total: number;
  completed: number;
  status: PlanStatus;
};

export type BootstrapResponse = {
  catalog_contract: 2;
  session_scope: string;
  latest_attempt_id: string | null;
  school: {
    brand: Brand;
    links: SchoolLinks;
  };
  diagnostics: PublicDiagnosticSummary[];
  progress_profile?: ProgressProfile;
  gameplay_profile?: GameplayProfile;
  daily_plan?: DailyPlanSummary | null;
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
  learning_material_text?: string | null;
  max_primary_score?: number;
  earned_primary_score?: number;
  source?: QuestionSourceAttribution;
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
