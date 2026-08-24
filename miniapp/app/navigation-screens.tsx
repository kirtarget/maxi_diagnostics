import { subjectIconKind, type SubjectIconKind } from "./subject-illustration";
import type {
  Brand,
  DiagnosticMode,
  PublicDiagnostic,
  SchoolLinks,
} from "./types";

export type WelcomeScreenProps = {
  diagnostics: PublicDiagnostic[];
  labels: Brand["interface"];
  links: SchoolLinks;
  onStart: () => void;
};

export function WelcomeScreen({
  diagnostics,
  labels,
  links,
  onStart,
}: WelcomeScreenProps) {
  const minimumQuestions = Math.min(...diagnostics.map((item) => item.quick_count));
  const maximumQuestions = Math.max(...diagnostics.map((item) => item.questions.length));
  const questionRange = minimumQuestions === maximumQuestions
    ? String(maximumQuestions)
    : `${minimumQuestions}–${maximumQuestions}`;
  const radarLabel = "Радар результата: сильные темы, пробелы и персональный план";

  return (
    <section className="screen welcome-screen radar-screen" aria-labelledby="welcome-title">
      <div className="welcome-copy">
        <span className="state-code">Подготовка к экзаменам</span>
        <h1 id="welcome-title">Ваш путь к успеху <em>на ОГЭ и ЕГЭ</em></h1>
        <p className="hero-copy">Выберите предмет, чтобы получить карту знаний, зоны роста, PDF-отчёт и план подготовки.</p>
      </div>
      <div className="radar" role="img" aria-label={radarLabel}>
        <span className="radar-ring radar-ring-one" />
        <span className="radar-ring radar-ring-two" />
        <span className="radar-axis radar-axis-horizontal" />
        <span className="radar-axis radar-axis-vertical" />
        <span className="radar-sweep" />
        <span className="radar-point radar-point-strong">Сильные темы</span>
        <span className="radar-point radar-point-gap">Пробелы</span>
        <span className="radar-point radar-point-plan">План</span>
      </div>
      <div className="welcome-facts" aria-label="Параметры диагностики">
        <div><strong>{questionRange}</strong><span>заданий</span></div>
        <div><strong>Без таймера</strong><span>свой темп</span></div>
        <div><strong>PDF</strong><span>в Telegram</span></div>
      </div>
      <button className="primary-button" onClick={onStart} type="button">
        {labels.start_diagnostic} <span aria-hidden="true">→</span>
      </button>
      <div className="utility-links">
        <a href={links.privacy} target="_blank" rel="noreferrer">{labels.privacy_label}</a>
        <a href={links.support} target="_blank" rel="noreferrer">{labels.support_label}</a>
      </div>
    </section>
  );
}

export type ModeScreenProps = {
  labels: Brand["interface"];
  onBack: () => void;
  onSelect: (mode: DiagnosticMode) => void;
};

export function ModeScreen({ labels, onBack, onSelect }: ModeScreenProps) {
  return (
    <section className="screen navigation-screen" aria-labelledby="mode-title">
      <button className="text-back" onClick={onBack} type="button">{labels.back}</button>
      <span className="state-code">01 / Формат</span>
      <h1 id="mode-title">Насколько подробно?</h1>
      <p className="lead">Выберите глубину проверки. Полная диагностика даёт более точную карту и разбор каждого задания.</p>
      <div className="mode-list">
        <button className="mode-card" onClick={() => onSelect("quick")} type="button">
          <span className="mode-badge">Быстрый замер</span>
          <strong>{labels.quick_result}</strong>
          <span>Короткий ориентир по основным темам без обещания полной картины.</span>
          <em>{labels.choose_label} →</em>
        </button>
        <button className="mode-card featured" onClick={() => onSelect("full")} type="button">
          <span className="mode-badge">Полная диагностика</span>
          <strong>{labels.full_result}</strong>
          <span>Все доступные задания, точная карта тем и полный разбор после результата.</span>
          <em>{labels.choose_label} →</em>
        </button>
      </div>
    </section>
  );
}

export type SubjectsScreenProps = {
  diagnostics: PublicDiagnostic[];
  exam: string;
  labels: Brand["interface"];
  mode: DiagnosticMode;
  onBack: () => void;
  onExam: (exam: string) => void;
  onSelect: (diagnostic: PublicDiagnostic) => void;
};

export function SubjectsScreen({
  diagnostics,
  exam,
  labels,
  mode,
  onBack,
  onExam,
  onSelect,
}: SubjectsScreenProps) {
  const exams = [...new Set(diagnostics.map((item) => item.exam))];
  const selectedExam = exams.includes(exam) ? exam : (exams[0] ?? "");
  const visibleDiagnostics = diagnostics.filter((item) => item.exam === selectedExam);

  return (
    <section className="screen navigation-screen" aria-labelledby="subject-title">
      <button className="text-back" onClick={onBack} type="button">{labels.back}</button>
      <span className="state-code">02 / Предмет</span>
      <h1 id="subject-title">Что будем проверять?</h1>
      <p className="lead">Выберите экзамен и предмет. У каждой диагностики есть сохранение прогресса и разбор результата.</p>
      {exams.length > 1 && (
        <div className="exam-tabs" role="tablist" aria-label="Экзамен">
          {exams.map((item) => (
            <button
              aria-selected={item === selectedExam}
              className={item === selectedExam ? "selected" : ""}
              key={item}
              onClick={() => onExam(item)}
              role="tab"
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
      )}
      <div className="subject-list">
        {visibleDiagnostics.map((item) => {
          const count = mode === "quick" ? item.quick_count : item.questions.length;
          return (
            <button className="subject-card" key={item.id} onClick={() => onSelect(item)} type="button">
              <SubjectIllustration subject={item.subject} />
              <span className="subject-copy">
                <strong>{item.subject}</strong>
                <small>{count} заданий · полный разбор</small>
              </span>
              <span className="subject-action">
                <span>{labels.start_diagnostic}</span><span aria-hidden="true">→</span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function SubjectIllustration({ subject }: { subject: string }) {
  const kind = subjectIconKind(subject);
  return (
    <span className="subject-illustration" data-subject={kind} aria-hidden="true">
      <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <SubjectIllustrationDrawing kind={kind} />
      </svg>
    </span>
  );
}

function SubjectIllustrationDrawing({ kind }: { kind: SubjectIconKind }) {
  if (kind === "biology") return <><path d="M10 32C11 17 22 9 38 10c-1 16-11 26-28 22Z" /><path d="M12 31 34 14" /><circle cx="29" cy="28" r="5" /></>;
  if (kind === "chemistry") return <><path d="M18 8h12M21 8v13L12 36a3 3 0 0 0 3 4h18a3 3 0 0 0 3-4l-9-15V8" /><path d="M16 32h16" /><circle cx="22" cy="27" r="1" /><circle cx="27" cy="34" r="1" /></>;
  if (kind === "english") return <><path d="M9 12h30v22H23l-8 6v-6H9Z" /><path d="m17 29 4-11 4 11M19 25h4M29 19h5M31.5 19v10" /></>;
  if (kind === "history") return <><path d="m7 17 17-9 17 9H7ZM10 37h28M7 41h34M13 18v19M21 18v19M29 18v19M37 18v19" /></>;
  if (kind === "informatics") return <><path d="m18 12-11 12 11 12M30 12l11 12-11 12M27 9l-6 30" /></>;
  if (kind === "literature") return <><path d="M7 11h12c4 0 5 3 5 6v23c0-4-3-6-7-6H7ZM41 11H29c-4 0-5 3-5 6v23c0-4 3-6 7-6h10Z" /><path d="M11 17h7M11 22h7M30 17h7M30 22h7" /></>;
  if (kind === "mathematics") return <><path d="M8 37 21 11l13 26ZM27 13h13M33.5 7v12M29 28h11M29 34h11" /><circle cx="13" cy="12" r="4" /></>;
  if (kind === "physics") return <><ellipse cx="24" cy="24" rx="18" ry="7" /><ellipse cx="24" cy="24" rx="18" ry="7" transform="rotate(60 24 24)" /><ellipse cx="24" cy="24" rx="18" ry="7" transform="rotate(120 24 24)" /><circle cx="24" cy="24" r="2.5" fill="currentColor" stroke="none" /></>;
  if (kind === "russian") return <><path d="m11 37 9-26h8l9 26M15 27h18" /><path d="M34 10h7M37.5 7v6" /></>;
  if (kind === "social") return <><circle cx="13" cy="17" r="5" /><circle cx="35" cy="17" r="5" /><circle cx="24" cy="10" r="5" /><path d="M5 38c1-8 5-12 11-12M43 38c-1-8-5-12-11-12M14 38c1-9 4-14 10-14s9 5 10 14" /></>;
  return <><circle cx="24" cy="24" r="15" /><path d="M24 14v20M14 24h20M17 17l14 14M31 17 17 31" /></>;
}
