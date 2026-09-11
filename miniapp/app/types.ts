/** Every screen the mini app can show. Owned by `page.tsx`, shared with its hooks. */
export type Screen =
  | "loading"
  | "diagnostic-loading"
  | "welcome"
  | "home"
  | "today"
  | "path"
  | "results"
  | "session-complete"
  | "checkpoint-result"
  | "profile"
  | "league"
  | "mode"
  | "subjects"
  | "question"
  | "submitting"
  | "result"
  | "review"
  | "forecast"
  | "plan"
  | "trainer";

export type DiagnosticMode = "quick" | "full";
export type QuestionType = "single" | "multiple" | "matching" | "input" | "text";

export type QuestionOption = {
  id: string;
  label: string;
  /** Optional display-only stress form. It never carries answer correctness. */
  stress?: string;
  /** A matching cell the editor drew. Present only where the label is empty. */
  asset?: string;
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
  asset_alt?: string;
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
  /** Contract-4 answer metadata. Older catalogs omit these fields. */
  answer_format?: "number" | "sequence";
  answer_unit?: string;
  answer_length?: number;
  allow_reuse?: boolean;
  markers?: string[];
};

/** Short written answer. The server holds every accepted spelling; `max_length` only sizes the field. */
export type TextQuestion = BaseQuestion & {
  type: "text";
  max_length?: number;
  answer_format?: "word" | "words";
  lang?: "ru" | "en";
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
  full_count: number;
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
    result_in_app: string;
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
  skipped_count: number;
  score: number;
  max_score: number;
  score_unit: string;
  unassessed_part?: string | null;
  /** Server-owned completion reward. Legacy snapshots may omit it. */
  xp_earned?: number;
  strong_topics: Array<ServerTopic | string>;
  growth_topics: Array<ServerTopic | string>;
  recoverable_primary_score?: number;
  estimate?: ScoreEstimate | null;
  per_question?: PublicQuestionOutcome[];
  forecast?: { kind?: ForecastKind; points: ForecastPoint[] } | Record<string, number>;
};

export type PublicQuestionOutcome = {
  question_id: string;
  number: number;
  topic: string;
  status: "correct" | "incorrect" | "skipped";
  is_correct: boolean;
};

export type DeliveryStatus = "pending" | "sending" | "sent" | "failed" | "abandoned";

export type ServerAttempt = {
  result?: ServerResult;
  exam?: string;
  subject?: string;
  completed_at?: string;
  attempt_id: string;
  diagnostic_id: string;
  content_version: string;
  mode: DiagnosticMode;
  status: "in_progress" | "completed";
  question_index: number;
  question_count: number;
  progress_revision: number;
  answers?: AnswerMap;
  estimate?: ScoreEstimate | null;
  pdf_status?: DeliveryStatus | null;
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

/** One node of the topic path. `done` topics are closed, exactly one is `current`, the rest are `locked`. */
export type TopicStatus = "done" | "current" | "locked";

export type TopicPathNode = {
  topic: string;
  /** Position in codifier order, starting at 0. */
  index: number;
  /** Questions of this topic in the diagnostic. */
  total: number;
  /** Questions of this topic answered correctly at least once. */
  mastered: number;
  status: TopicStatus;
  /** ISO date the topic was closed, or null while it is open. */
  done_at: string | null;
};

/**
 * One weekly-checkpoint node, one per unit of the path.
 * `locked` until every unit topic is done, then `available`, unless another
 * checkpoint was passed within the week (`cooldown`); `passed` once cleared.
 */
export type CheckpointStatus = "locked" | "available" | "cooldown" | "passed";

/** A unit checkpoint on the path, from `POST /api/diagnostics/path`. */
export type CheckpointNode = {
  unit_index: number;
  /** Inclusive path-index range of the unit's topics. */
  topic_from: number;
  topic_to: number;
  topics: string[];
  status: CheckpointStatus;
  /** ISO instant the cooldown lifts, or null when not throttled. */
  available_at: string | null;
  /** ISO instant the checkpoint was passed, or null. */
  passed_at: string | null;
  /** How many срез questions were answered right (named to avoid the `correct` key). */
  mastered_count: number | null;
  question_total: number | null;
};

/** Ordered topic path for one diagnostic, from `POST /api/diagnostics/path`. */
export type TopicPathResponse = {
  diagnostic_id: string;
  content_version: string;
  subject: string;
  exam: string;
  current_topic: string | null;
  done_count: number;
  total_count: number;
  topics: TopicPathNode[];
  /** One node per unit; the path screen renders these as real nodes. */
  checkpoints: CheckpointNode[];
};

export type TodaySessionStatus = "ready" | "checkpoint" | "path_complete" | "no_diagnostic";

/** Today's session descriptor for the home screen, from `POST /api/diagnostics/today`. */
export type TodaySession = {
  status: TodaySessionStatus;
  diagnostic_id: string | null;
  content_version: string | null;
  subject: string | null;
  exam: string | null;
  /** The current topic the session trains, or null when the path is complete. */
  topic: string | null;
  topic_total: number;
  topic_mastered: number;
  /** How many questions the session serves. Start it with `startTrainer(..., { mode: "today", count: size })`. */
  size: number;
  estimated_minutes: number;
  /** Reused gameplay fields so the home card needs no extra call. */
  streak_days: number;
  daily_goal: GameplayDailyGoal;
  xp_total: number;
  /** The full path, so home can render its preview from one response. */
  path: TopicPathNode[];
  /** One node per unit; mirrors the `/path` checkpoints. */
  checkpoints: CheckpointNode[];
  /** The unit whose checkpoint is available or in cooldown, when `status` is `checkpoint`. */
  checkpoint_unit_index: number | null;
};

/** A started checkpoint session, from `POST /api/diagnostics/checkpoint/start`. */
export type CheckpointStartResponse = {
  ok: true;
  trainer_session_id: string;
  diagnostic_id: string;
  content_version: string;
  mode: "checkpoint";
  topic: string | null;
  source_attempt_id: string | null;
  question_ids: string[];
  current_index: number;
  revision: number;
  status: "active" | "exhausted" | "completed";
  unit_index: number;
  /** Answer each with `answerTrainer(...)`; scoring stays on the server. */
  questions: Question[];
  lives_remaining: number;
  next_life_at: string | null;
};

/** The checkpoint outcome, from `POST /api/diagnostics/checkpoint/record`. */
export type CheckpointRecordResponse = {
  ok: true;
  passed: boolean;
  unit_index: number;
  mastered_count: number;
  question_total: number;
  /** The unit's checkpoint node after recording, or null if the unit vanished. */
  checkpoint: CheckpointNode | null;
  checkpoints: CheckpointNode[];
};

export type BootstrapResponse = {
  onboarding?: { status: "welcome" | "selection" | "completed" };
  catalog_contract: 3 | 4;
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
  asset_alt?: string;
  is_correct: boolean;
  status: "correct" | "incorrect" | "skipped";
  user_answer: string;
  expected_answer: string;
  guidance: string;
  guidance_kind: "individual" | "fallback";
  learning_material_text?: string | null;
  max_primary_score?: number;
  earned_primary_score?: number;
  source?: QuestionSourceAttribution;
  answer_preview?: ReviewAnswerPreview;
};

export type ReviewAnswerPreview = {
  kind: "matching" | "multiple" | "sequence";
  markers: string[];
  user: string[];
  expected: string[];
  option_labels?: Record<string, string>;
};

export type ReviewResponse = {
  ok: true;
  available: boolean;
  items: ReviewItem[];
  pdf_status: DeliveryStatus | null;
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
