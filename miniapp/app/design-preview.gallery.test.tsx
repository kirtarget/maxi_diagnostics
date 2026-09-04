// Visual-verification lever: renders every screen with fixture data into a
// static HTML gallery so the design can be reviewed without Telegram initData
// or a backend. Doubles as a render smoke test for all screens.
// Usage: DESIGN_PREVIEW_DIR=<dir> npx vitest run app/design-preview.gallery.test.tsx
// then copy public/fonts into <dir> and open <dir>/index.html.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GameplayHomeScreen, GameplayProfileScreen, ModeScreen, NotTelegramScreen, SubjectsScreen, WelcomeScreen } from "./navigation-screens";
import { QuestionView } from "./question-screen";
import { ForecastEmptyScreen, ForecastScreen, ResultScreen, ReviewScreen, RouteScreen } from "./result-flow";
import { TrainerScreen } from "./trainer-screen";
import { LeagueScreen } from "./league-screen";
import { gameplayProfileView } from "./gameplay-profile-model";
import brand from "../../school/brand.json";
import schoolLinks from "../../school/links.json";
import type { Brand, PublicDiagnostic, Question, QuestionSourceAttribution, ServerResult } from "./types";

const OUT_DIR = process.env.DESIGN_PREVIEW_DIR ?? "";

const labels = brand.interface as unknown as Brand["interface"];
const links = schoolLinks;

const approvedSource: QuestionSourceAttribution = {
  provider: "maximum",
  official_year: 2026,
  approval_status: "approved",
  source_kind: "original",
  source_url: "https://maximumtest.ru/",
  rights_status: "original",
  verified_at: "2026-09-01",
};

const q = (id: string, extra: Partial<Question> = {}): Question => ({
  id,
  type: "single",
  topic: "Квадратные уравнения",
  title: `Задание ${id}`,
  prompt: "Решите уравнение x^2 − 5x + 6 = 0. В ответе укажите меньший корень.",
  max_primary_score: 2,
  source: approvedSource,
  options: [
    { id: "a", label: "2" },
    { id: "b", label: "3" },
    { id: "c", label: "5" },
    { id: "d", label: "6" },
  ],
  ...extra,
} as Question);

const diagnostics: PublicDiagnostic[] = [
  { id: "math", content_version: "v1", exam: "ОГЭ", subject: "Математика", mark: "М", quick_count: 10, full_count: 24, question_count: 24, questions: Array.from({ length: 24 }, (_, i) => q(String(i + 1))) },
  { id: "rus", content_version: "v1", exam: "ОГЭ", subject: "Русский язык", mark: "Р", quick_count: 10, full_count: 20, question_count: 20, questions: Array.from({ length: 20 }, (_, i) => q(`r${i + 1}`)) },
  { id: "phys", content_version: "v1", exam: "ОГЭ", subject: "Физика", mark: "Ф", quick_count: 10, full_count: 24, question_count: 24, questions: Array.from({ length: 24 }, (_, i) => q(`p${i + 1}`)) },
  { id: "chem", content_version: "v1", exam: "ЕГЭ", subject: "Химия", mark: "Х", quick_count: 10, full_count: 22, question_count: 22, questions: Array.from({ length: 22 }, (_, i) => q(`c${i + 1}`)) },
];

const profile = gameplayProfileView({
  completion_count: 8,
  achievement_keys: ["first_diagnostic_completed"],
  xp_total: 1240,
  level: 7,
  level_progress: 78,
  streak_days: 5,
  lives_remaining: 4,
  daily_goal: { date: null, target: 50, progress: 30, complete: false },
  quest: { key: "complete_3_activities", date: null, target: 3, progress: 1 },
});

const result: ServerResult = {
  score: 74,
  max_score: 100,
  score_unit: "баллов",
  correct_count: 18,
  question_count: 24,
  estimate: { kind: "test_score", value: 62, scaled_primary: 24, exam_max_primary: 32, sample_max_primary: 30, sample_size: 24, min_pass: 27 },
  strong_topics: ["Линейные уравнения", "Проценты", "Графики"],
  growth_topics: ["Квадратные уравнения", "Геометрия · площади"],
  unassessed_part: "",
} as unknown as ServerResult;

const tableGapPrompt = [
  "Заполните пропуски в таблице «Свойства веществ».",
  "Вещество",
  "Формула",
  "Агрегатное состояние",
  "Кислород",
  "O2",
  "(А)",
  "(Б)",
  "H2O",
  "жидкость",
  "Железо",
  "Fe",
  "(В)",
  "Пропущенные элементы:",
  "1) газ;",
  "2) вода;",
  "3) твёрдое.",
].join("\n");

const noop = () => undefined;

const screens: Array<[string, string]> = [
  ["welcome", renderToStaticMarkup(<WelcomeScreen diagnostics={diagnostics} labels={labels} links={links} onStart={noop} />)],
  ["home", renderToStaticMarkup(<GameplayHomeScreen diagnostics={diagnostics} labels={labels} profile={profile} onStart={noop} onOpenProfile={noop} onOpenLeague={noop} offers={links.offers} />)],
  ["profile", renderToStaticMarkup(<GameplayProfileScreen profile={profile} onBack={noop} onStart={noop} />)],
  ["mode", renderToStaticMarkup(<ModeScreen labels={labels} onBack={noop} onSelect={noop} />)],
  ["subjects", renderToStaticMarkup(<SubjectsScreen diagnostics={diagnostics} exam="ОГЭ" labels={labels} mode="full" onBack={noop} onExam={noop} onSelect={noop} />)],
  ["question-single", renderToStaticMarkup(<QuestionView question={q("3")} index={2} total={10} answer="b" labels={labels} onAnswer={noop} onBack={noop} onNext={noop} />)],
  ["question-input", renderToStaticMarkup(<QuestionView question={q("5", { type: "input", options: undefined, prompt: "Найди значение выражения 2,4 · 5 − 3,6. Запиши ответ числом." } as never)} index={4} total={10} answer="8,4" labels={labels} onAnswer={noop} onBack={noop} onNext={noop} />)],
  ["question-tablegap", renderToStaticMarkup(<QuestionView question={q("9", { type: "input", options: undefined, prompt: tableGapPrompt, topic: "Химия" } as never)} index={8} total={10} answer="1" labels={labels} onAnswer={noop} onBack={noop} onNext={noop} />)],
  ["question-text", renderToStaticMarkup(<QuestionView question={q("7", { type: "text", options: undefined, max_length: 40, topic: "Союзы", prompt: "Выпишите подчинительный союз из предложения." } as never)} index={6} total={10} answer="однако" labels={labels} onAnswer={noop} onBack={noop} onNext={noop} />)],
  ["result", renderToStaticMarkup(<ResultScreen diagnostic={diagnostics[0]} pdfStatus="pending" result={result} onReview={noop} onForecast={noop} onReplayMistakes={noop} />)],
  ["review", renderToStaticMarkup(<ReviewScreen items={[{ question_id: "q8", number: 8, type: "single", topic: "Квадратные уравнения", title: "Задание 8", prompt: "Решите уравнение x² + 4x − 5 = 0. Укажите больший корень.", is_correct: false, user_answer: "−5", expected_answer: "1", guidance: "По теореме Виета: x₁ · x₂ = −5, x₁ + x₂ = −4. Корни: 1 и −5. Больший из них — 1.", guidance_kind: "fallback", max_primary_score: 2, earned_primary_score: 0, source: approvedSource }]} index={0} onBack={noop} onNext={noop} onForecast={noop} />)],
  ["review-clean", renderToStaticMarkup(<ReviewScreen items={[]} index={0} onBack={noop} onNext={noop} onForecast={noop} />)],
  ["forecast", renderToStaticMarkup(<ForecastScreen points={[{ id: "current", label: "Сейчас", value: 74 }, { id: "goal", label: "Цель", value: 85 }]} offers={links.offers} onBack={noop} onRoute={noop} />)],
  ["forecast-empty", renderToStaticMarkup(<ForecastEmptyScreen completedCount={1} onBack={noop} onStart={noop} />)],
  ["not-telegram", renderToStaticMarkup(<NotTelegramScreen botUrl="https://t.me/maxi_diagnostics_bot" />)],
  ["trainer-no-lives", renderToStaticMarkup(<TrainerScreen state={{
    phase: "answering",
    session: { trainer_session_id: "t", revision: 1, mode: "normal", lives_remaining: 0, next_life_at: new Date(Date.now() + 42 * 60_000).toISOString(), question_ids: ["a"], questions: [q("a")] },
    currentIndex: 0,
    answeredQuestionIndex: null,
    draftAnswer: undefined,
    submittedAnswer: undefined,
    answerResult: null,
    finishResult: null,
    error: null,
    retryPhase: null,
  } as never} dispatch={noop} livesReminder={{ status: "idle" }} onRemindLives={noop} offers={links.offers} />)],
  ["route", renderToStaticMarkup(<RouteScreen items={[{ id: "close-topic", title: "Квадратные уравнения", description: "Зона роста: начни с тренажёра по этой теме." }, { id: "strengthen-topic", title: "Геометрия · площади", description: "Повтори формулы площадей и реши подборку." }]} pdf={{ title: "PDF-отчёт готовится", description: "Пришлём в Telegram, когда будет готов." }} offers={links.offers} onRefreshPdf={noop} onSubjects={noop} />)],
  ["trainer-feedback", renderToStaticMarkup(<TrainerScreen state={{
    phase: "feedback",
    session: { trainer_session_id: "t", revision: 2, mode: "normal", lives_remaining: 4, question_ids: ["a", "b", "c", "d", "e"], questions: [q("a", { prompt: "Чему равно значение выражения 3 · (4 + 2)?", options: [{ id: "a", label: "14" }, { id: "b", label: "18" }, { id: "c", label: "20" }] } as never), q("b"), q("c"), q("d"), q("e")] },
    currentIndex: 1,
    answeredQuestionIndex: 0,
    draftAnswer: "b",
    submittedAnswer: "b",
    answerResult: { is_correct: false, correct_answer: "18", explanation: "Сначала скобки: 4 + 2 = 6, затем умножение: 3 · 6 = 18.", max_primary_score: 2, earned_primary_score: 0, xp_delta: 0, lives_remaining: 4, revision: 2 },
    finishResult: null,
    error: null,
    retryPhase: "answering",
  } as never} dispatch={noop} offers={links.offers} />)],
  ["league", renderToStaticMarkup(<LeagueScreen state={{ kind: "ready", data: { status: "active", week_start: "21 августа", week_end: "27 августа", rows: [
    { rank: 1, display_label: "Аня К.", xp_week: 2480, is_me: false },
    { rank: 2, display_label: "Дима С.", xp_week: 2120, is_me: false },
    { rank: 3, display_label: "Марк В.", xp_week: 1890, is_me: false },
    { rank: 4, display_label: "Кир", xp_week: 1240, is_me: true },
    { rank: 5, display_label: "Лиза Т.", xp_week: 980, is_me: false },
  ], me: { rank: 4, xp_week: 1240 } } }} onHome={noop} />)],
];

describe("design preview gallery", () => {
  it("writes the gallery when DESIGN_PREVIEW_DIR is set", () => {
    if (!OUT_DIR) return;
    mkdirSync(OUT_DIR, { recursive: true });
    const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8")
      .replace(/url\("\/fonts\//g, 'url("fonts/');
    writeFileSync(`${OUT_DIR}/globals.css`, css);
    const style = brand.colors;
    const vars = `--brand-primary:${style.primary};--brand-accent:${style.accent};--brand-signal:${style.signal};--brand-ink:${style.ink};--brand-paper:${style.paper};--brand-background:${style.background}`;
    for (const [name, html] of screens) {
      writeFileSync(`${OUT_DIR}/${name}.html`, `<!doctype html><html lang="ru" style="${vars}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="globals.css"></head><body><main class="app-shell">${name === "question-single" || name === "question-input" || name === "question-tablegap" || name === "question-text" ? "" : '<header class="brand-bar"><button class="brand" type="button"><span class="brand-mark">MA</span><span>MAXIMUM Education</span></button><span class="status-pill">Результат в Telegram</span></header>'}${html}</main></body></html>`);
    }
    writeFileSync(`${OUT_DIR}/index.html`, `<!doctype html><meta charset="utf-8"><body style="margin:0;display:grid;grid-template-columns:repeat(auto-fill,400px);gap:20px;background:#ddd;padding:20px">${screens.map(([name]) => `<div><p style="font:700 13px sans-serif;margin:0 0 6px">${name}</p><iframe src="${name}.html" style="width:390px;height:844px;border:1px solid #999;border-radius:20px;background:#fff"></iframe></div>`).join("")}</body>`);
    expect(screens.length).toBeGreaterThan(0);
  });
});
